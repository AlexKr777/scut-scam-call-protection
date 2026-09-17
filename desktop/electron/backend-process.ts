import { spawn } from 'node:child_process'
import { win32 as winPath, posix as posixPath } from 'node:path'

export interface PythonCandidate {
  label: string
  command: string
  prefixArgs: string[]
}

export interface ManagedChild {
  pid?: number
  killed: boolean
  exitCode?: number | null
  kill(signal?: NodeJS.Signals | number): boolean
}

export interface BackendHandle {
  baseUrl: string
  port: number
  ownsProcess: boolean
  child?: ManagedChild
  runtimeLabel?: string
}

export interface BackendRuntime {
  probeHealth(baseUrl: string): Promise<boolean>
  launch(candidate: PythonCandidate, serverArgs: string[], cwd: string): ManagedChild
  waitForHealth(
    baseUrl: string,
    timeoutMs: number,
    candidate: PythonCandidate,
    child: ManagedChild,
  ): Promise<boolean>
}

export interface EnsureBackendOptions {
  projectRoot: string
  port: number
  environment?: NodeJS.ProcessEnv
  platform?: NodeJS.Platform
  runtime?: BackendRuntime
  startupTimeoutMs?: number
}

const sleep = (durationMs: number) => new Promise((resolve) => setTimeout(resolve, durationMs))

export function pythonCandidates(
  projectRoot: string,
  environment: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform,
): PythonCandidate[] {
  const pathApi = platform === 'win32' ? winPath : posixPath
  const candidates: PythonCandidate[] = []
  const configured = environment.SCUT_PYTHON_PATH?.trim()
  if (configured) {
    return [{ label: 'SCUT_PYTHON_PATH', command: configured, prefixArgs: [] }]
  }
  candidates.push({
    label: 'project venv',
    command: pathApi.join(projectRoot, '.local', 'venv', platform === 'win32' ? 'Scripts' : 'bin', platform === 'win32' ? 'python.exe' : 'python'),
    prefixArgs: [],
  })
  if (platform === 'win32') {
    candidates.push({ label: 'Python launcher 3.12', command: 'py', prefixArgs: ['-3.12'] })
  }
  candidates.push({ label: 'PATH python', command: 'python', prefixArgs: [] })
  return candidates
}

async function probeHealth(baseUrl: string): Promise<boolean> {
  try {
    const response = await fetch(`${baseUrl}/health`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(800),
    })
    if (!response.ok) return false
    const payload = (await response.json()) as { ok?: unknown; protocolVersion?: unknown }
    return payload.ok === true && payload.protocolVersion === 1
  } catch {
    return false
  }
}

const defaultRuntime: BackendRuntime = {
  probeHealth,
  launch(candidate, serverArgs, cwd) {
    const child = spawn(candidate.command, [...candidate.prefixArgs, ...serverArgs], {
      cwd,
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
      stdio: 'ignore',
      windowsHide: true,
    })
    child.on('error', () => undefined)
    return child
  },
  async waitForHealth(baseUrl, timeoutMs, _candidate, child) {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      if (await probeHealth(baseUrl)) return true
      if (child.exitCode !== null && child.exitCode !== undefined) return false
      await sleep(125)
    }
    return false
  },
}

export async function ensureBackend(options: EnsureBackendOptions): Promise<BackendHandle> {
  const baseUrl = `http://127.0.0.1:${options.port}`
  const runtime = options.runtime ?? defaultRuntime
  if (await runtime.probeHealth(baseUrl)) {
    return { baseUrl, port: options.port, ownsProcess: false }
  }

  const attempted: string[] = []
  for (const candidate of pythonCandidates(
    options.projectRoot,
    options.environment,
    options.platform,
  )) {
    attempted.push(candidate.label)
    let child: ManagedChild | undefined
    try {
      child = runtime.launch(
        candidate,
        ['backend/server.py', '--host', '127.0.0.1', '--port', String(options.port)],
        options.projectRoot,
      )
      const healthy = await runtime.waitForHealth(
        baseUrl,
        options.startupTimeoutMs ?? 8_000,
        candidate,
        child,
      )
      if (healthy) {
        return {
          baseUrl,
          port: options.port,
          ownsProcess: true,
          child,
          runtimeLabel: candidate.label,
        }
      }
    } catch {
      // A copied venv or unavailable launcher is expected to fail closed.
    }
    if (child && !child.killed) child.kill()
  }

  throw new Error(`SCUT backend did not start. Tried: ${attempted.join(', ')}`)
}

export function stopOwnedBackend(handle: BackendHandle | undefined): void {
  if (handle?.ownsProcess && handle.child && !handle.child.killed) {
    handle.child.kill()
  }
}
