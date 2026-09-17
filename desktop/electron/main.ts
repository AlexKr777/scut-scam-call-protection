import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { app, BrowserWindow, ipcMain, Menu, screen, session } from 'electron/main'
import { ensureBackend, stopOwnedBackend, type BackendHandle } from './backend-process.js'
import { parseCaptureOptions } from './capture-options.js'
import { floatingBarBounds, isFloatingBarSize, type FloatingBarSize } from './floating-bar-geometry.js'
import { resolveLocalRuntimeDirectory } from './local-runtime.js'
import { useDevelopmentRenderer } from './runtime-mode.js'

const currentDirectory = dirname(fileURLToPath(import.meta.url))
const desktopRoot = resolve(currentDirectory, '..', '..')
// The installed renderer lives in resources/app, while the authoritative
// Python source is explicitly placed beside it as a read-only runtime asset.
// Development keeps the existing repository-relative layout.
const projectRoot = app.isPackaged
  ? join(process.resourcesPath, 'scut-runtime')
  : resolve(desktopRoot, '..')
if (app.isPackaged) {
  app.setPath('userData', resolveLocalRuntimeDirectory(process.env, app.getPath('appData')))
}
const preferredPort = Number(process.env.SCUT_PORT ?? 8765)
const captureOptions = parseCaptureOptions(process.argv)
let backend: BackendHandle | undefined
let backendFailure: string | undefined
let captureStarted = false
let mainWindow: BrowserWindow | undefined
let floatingBarWindow: BrowserWindow | undefined
let floatingResizeTimer: NodeJS.Timeout | undefined

if (captureOptions) {
  app.commandLine.appendSwitch('force-device-scale-factor', String(captureOptions.scaleFactor))
}

async function backendJson(pathname: string): Promise<unknown> {
  if (backendFailure) throw new Error(backendFailure)
  const baseUrl = backend?.baseUrl ?? `http://127.0.0.1:${preferredPort}`
  const response = await fetch(`${baseUrl}${pathname}`, {
    cache: 'no-store',
    signal: AbortSignal.timeout(5_000),
  })
  if (!response.ok) throw new Error(`Backend request failed (${response.status})`)
  return response.json()
}

async function backendPost(pathname: string, body: Record<string, unknown>): Promise<unknown> {
  if (backendFailure) throw new Error(backendFailure)
  const baseUrl = backend?.baseUrl ?? `http://127.0.0.1:${preferredPort}`
  const response = await fetch(`${baseUrl}${pathname}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10_000),
  })
  const result = await response.json() as { error?: { message?: string } }
  if (!response.ok) throw new Error(result.error?.message ?? `SCUT request failed (${response.status})`)
  return result
}

async function submitCaptureTranscript(text: string): Promise<void> {
  const baseUrl = backend?.baseUrl ?? `http://127.0.0.1:${preferredPort}`
  const response = await fetch(`${baseUrl}/api/transcripts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
    signal: AbortSignal.timeout(5_000),
  })
  if (!response.ok) throw new Error(`Capture transcript input failed (${response.status})`)
}

function realtimeEndpoint(): string {
  const baseUrl = backend?.baseUrl ?? `http://127.0.0.1:${preferredPort}`
  return `${baseUrl.replace(/^http/, 'ws')}/ws`
}

function displayForFloatingBar() {
  const anchor = mainWindow && !mainWindow.isDestroyed()
    ? mainWindow.getBounds()
    : screen.getPrimaryDisplay().bounds
  return screen.getDisplayMatching(anchor)
}

function resizeFloatingBar(size: FloatingBarSize): void {
  if (!floatingBarWindow || floatingBarWindow.isDestroyed()) return
  if (floatingResizeTimer) clearTimeout(floatingResizeTimer)

  const window = floatingBarWindow
  const initial = window.getBounds()
  const target = floatingBarBounds(displayForFloatingBar().workArea, size)
  const startedAt = Date.now()
  const durationMs = 220
  const easeOut = (progress: number) => 1 - (1 - progress) ** 3

  const animate = () => {
    if (window.isDestroyed()) return
    const progress = Math.min(1, (Date.now() - startedAt) / durationMs)
    const eased = easeOut(progress)
    window.setBounds({
      x: Math.round(initial.x + (target.x - initial.x) * eased),
      y: Math.round(initial.y + (target.y - initial.y) * eased),
      width: Math.round(initial.width + (target.width - initial.width) * eased),
      height: Math.round(initial.height + (target.height - initial.height) * eased),
    })
    if (progress < 1) floatingResizeTimer = setTimeout(animate, 16)
  }

  animate()
}

async function captureWindow(window: BrowserWindow): Promise<void> {
  if (!captureOptions || captureStarted) return
  captureStarted = true

  if (captureOptions.transcriptInput) {
    await submitCaptureTranscript(captureOptions.transcriptInput)
  }
  if (captureOptions.delayMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, captureOptions.delayMs))
  }

  const contentBounds = window.getContentBounds()
  const image = await window.webContents.capturePage({
    x: 0,
    y: 0,
    width: captureOptions.surface === 'floating' ? contentBounds.width : captureOptions.width,
    height: captureOptions.surface === 'floating' ? contentBounds.height : captureOptions.height,
  })
  await mkdir(dirname(captureOptions.outputPath), { recursive: true })
  await writeFile(captureOptions.outputPath, image.toPNG())
  app.quit()
}

function registerBackendBridge(): void {
  ipcMain.handle('scut:get-health', () => backendJson('/health'))
  ipcMain.handle('scut:get-status', () => backendJson('/api/status'))
  ipcMain.handle('scut:get-realtime-endpoint', () => realtimeEndpoint())
  ipcMain.handle('scut:set-mode', (_event, mode: unknown) => {
    if (mode !== 'OFF' && mode !== 'TEST' && mode !== 'PROTECT') throw new Error('Unsupported protection mode.')
    return backendPost('/api/mode', { mode })
  })
  ipcMain.handle('scut:create-pairing', () => backendPost('/api/pair', {}))
  ipcMain.handle('scut:run-diagnostic', (_event, name: unknown) => {
    const diagnostics = new Set(['capture', 'earbuds', 'network', 'predemo', 'guarded-transcription'])
    if (typeof name !== 'string' || !diagnostics.has(name)) throw new Error('Unsupported diagnostic.')
    return backendPost(`/api/diagnostics/${name}`, { source: 'EXPLICIT_TEST_BUTTON' })
  })
  ipcMain.handle('scut:test-android-alert', () => backendPost('/api/alerts/test', {}))
  ipcMain.handle('scut:submit-diagnostic-transcript', (_event, text: unknown) => {
    if (typeof text !== 'string' || !text.trim() || text.length > 4_000) throw new Error('Diagnostic transcript must contain 1 to 4000 characters.')
    return backendPost('/api/transcripts', { text: text.trim() })
  })
  ipcMain.handle('scut:get-recording-url', () => `${backend?.baseUrl ?? `http://127.0.0.1:${preferredPort}`}/api/diagnostics/recording`)
  ipcMain.handle('scut:get-history', (_event, cursor: unknown) => {
    if (cursor !== undefined && (typeof cursor !== 'string' || cursor.length > 64)) throw new Error('Unsupported history cursor.')
    return backendJson(`/api/history?limit=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`)
  })
  ipcMain.handle('scut:get-alerts', (_event, cursor: unknown) => {
    if (cursor !== undefined && (typeof cursor !== 'string' || cursor.length > 64)) throw new Error('Unsupported alerts cursor.')
    return backendJson(`/api/alerts?limit=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`)
  })
  ipcMain.handle('scut:get-conversation', (_event, id: unknown) => {
    if (typeof id !== 'string' || !/^[0-9a-f-]{36}$/i.test(id)) throw new Error('Unsupported conversation id.')
    return backendJson(`/api/history/${id}`)
  })
  ipcMain.handle('scut:delete-conversation', (_event, id: unknown) => {
    if (typeof id !== 'string' || !/^[0-9a-f-]{36}$/i.test(id)) throw new Error('Unsupported conversation id.')
    return backendPost('/api/history/delete', { conversationId: id })
  })
  ipcMain.handle('scut:resize-floating-bar', (event, size: unknown) => {
    if (BrowserWindow.fromWebContents(event.sender) !== floatingBarWindow) {
      throw new Error('Only the Floating Bar can request its window size.')
    }
    if (!isFloatingBarSize(size)) throw new Error('Unsupported Floating Bar size.')
    resizeFloatingBar(size)
  })
  ipcMain.handle('scut:show-main-window', () => {
    if (!mainWindow || mainWindow.isDestroyed()) createMainWindow()
    mainWindow?.show()
    mainWindow?.focus()
  })

  if (captureOptions) {
    ipcMain.on('scut:visual-ready', async (event) => {
      if (captureOptions.surface !== 'main') return
      const window = BrowserWindow.fromWebContents(event.sender)
      if (!window) throw new Error('Capture renderer is not attached to a window.')
      await captureWindow(window)
    })
    ipcMain.on('scut:floating-bar-ready', async (event) => {
      if (captureOptions.surface !== 'floating') return
      const window = BrowserWindow.fromWebContents(event.sender)
      if (!window || window !== floatingBarWindow) throw new Error('Capture renderer is not the Floating Bar.')
      await captureWindow(window)
    })
  }
}

function loadRenderer(window: BrowserWindow, surface?: 'floating-bar'): void {
  const query = new URLSearchParams()
  if (surface) query.set('surface', surface)
  if (!surface && captureOptions?.page) query.set('page', captureOptions.page)
  if (captureOptions?.language) query.set('lang', captureOptions.language)
  if (useDevelopmentRenderer(process.argv)) {
    const url = new URL(process.env.SCUT_VITE_DEV_SERVER_URL ?? 'http://127.0.0.1:5173')
    query.forEach((value, key) => url.searchParams.set(key, value))
    void window.loadURL(url.toString())
  } else {
    const search = query.size ? query.toString() : undefined
    void window.loadFile(join(desktopRoot, 'dist', 'index.html'), search ? { search } : undefined)
  }
}

function createMainWindow(): BrowserWindow {
  const window = new BrowserWindow({
    title: 'SCUT',
    width: captureOptions?.width ?? 1360,
    height: captureOptions?.height ?? 860,
    useContentSize: Boolean(captureOptions),
    minWidth: 1080,
    minHeight: 720,
    show: false,
    backgroundColor: '#F4F1E7',
    autoHideMenuBar: true,
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#ECE7DA',
      symbolColor: '#35372F',
      height: 44,
    },
    webPreferences: {
      preload: join(currentDirectory, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  window.webContents.on('will-navigate', (event, navigationUrl) => {
    const currentUrl = window.webContents.getURL()
    if (currentUrl && new URL(navigationUrl).origin !== new URL(currentUrl).origin) {
      event.preventDefault()
    }
  })

  window.once('ready-to-show', () => window.show())
  window.on('closed', () => { if (mainWindow === window) mainWindow = undefined })
  mainWindow = window
  loadRenderer(window)
  return window
}

function createFloatingBarWindow(): BrowserWindow {
  const initialSize: FloatingBarSize = { width: 196, height: 48 }
  const bounds = floatingBarBounds(displayForFloatingBar().workArea, initialSize)
  const window = new BrowserWindow({
    title: 'SCUT Voice Bar',
    ...bounds,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    show: false,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: join(currentDirectory, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  window.setAlwaysOnTop(true, 'floating')
  window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  window.webContents.on('will-navigate', (event, navigationUrl) => {
    const currentUrl = window.webContents.getURL()
    if (currentUrl && new URL(navigationUrl).origin !== new URL(currentUrl).origin) event.preventDefault()
  })
  window.once('ready-to-show', () => window.showInactive())
  window.on('closed', () => { if (floatingBarWindow === window) floatingBarWindow = undefined })
  floatingBarWindow = window
  loadRenderer(window, 'floating-bar')
  return window
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null)
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false)
  })
  if (app.isPackaged) {
    const localRuntime = app.getPath('userData')
    process.env.SCUT_LOCAL_DIR = localRuntime
    process.env.SCUT_PYTHON_PATH = join(projectRoot, 'runtime', 'python.exe')
  }
  try {
    backend = await ensureBackend({ projectRoot, port: preferredPort })
  } catch (error) {
    backendFailure = error instanceof Error ? error.message : 'SCUT backend did not start.'
  }
  registerBackendBridge()
  createMainWindow()
  createFloatingBarWindow()

  app.on('activate', () => {
    if (!mainWindow || mainWindow.isDestroyed()) createMainWindow()
    if (!floatingBarWindow || floatingBarWindow.isDestroyed()) createFloatingBarWindow()
  })
})

app.on('before-quit', () => stopOwnedBackend(backend))

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
