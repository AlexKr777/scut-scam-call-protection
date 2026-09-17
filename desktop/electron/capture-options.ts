export interface CaptureOptions {
  outputPath: string
  width: number
  height: number
  scaleFactor: number
  delayMs: number
  transcriptInput?: string
  surface: 'main' | 'floating'
  page?: 'Home' | 'History' | 'Alerts' | 'Devices' | 'Settings'
  language?: 'en' | 'ru' | 'ro'
}

function valueFor(argv: readonly string[], name: string): string | undefined {
  const prefix = `--${name}=`
  return argv.find((argument) => argument.startsWith(prefix))?.slice(prefix.length)
}

function finiteNumber(value: string | undefined, fallback: number): number {
  if (value === undefined) return fallback
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) throw new Error('Capture options must be finite numbers.')
  return parsed
}

export function parseCaptureOptions(argv: readonly string[]): CaptureOptions | undefined {
  const outputPath = valueFor(argv, 'capture-output')
  if (!outputPath) return undefined

  const width = finiteNumber(valueFor(argv, 'capture-width'), 1440)
  const height = finiteNumber(valueFor(argv, 'capture-height'), 900)
  const scaleFactor = finiteNumber(valueFor(argv, 'capture-scale'), 1)
  const delayMs = finiteNumber(valueFor(argv, 'capture-delay-ms'), 0)
  const transcriptInput = valueFor(argv, 'capture-transcript')?.trim()
  const surface = valueFor(argv, 'capture-surface') ?? 'main'
  const pageValue = valueFor(argv, 'capture-page')
  const page = pageValue === undefined ? undefined : ['Home', 'History', 'Alerts', 'Devices', 'Settings'].includes(pageValue) ? pageValue as CaptureOptions['page'] : undefined
  const languageValue = valueFor(argv, 'capture-language')
  const language = languageValue === undefined ? undefined : ['en', 'ru', 'ro'].includes(languageValue) ? languageValue as CaptureOptions['language'] : undefined

  const isDesignedFloatingSize = (width === 196 && height === 48) || (width === 332 && height === 58)
  if (!Number.isInteger(width) || !Number.isInteger(height) || (surface === 'floating'
    ? !isDesignedFloatingSize
    : width < 1080 || height < 720)) {
    throw new Error('Capture viewport must use integer dimensions of at least 1080 x 720.')
  }
  if (scaleFactor < 1 || scaleFactor > 2) {
    throw new Error('Capture scale must be between 1 and 2.')
  }
  if (!Number.isInteger(delayMs) || delayMs < 0 || delayMs > 10_000) {
    throw new Error('Capture delay must be an integer between 0 and 10000 milliseconds.')
  }
  if (transcriptInput !== undefined && (!transcriptInput || transcriptInput.length > 4_000)) {
    throw new Error('Capture transcript must contain between 1 and 4000 characters.')
  }
  if (surface !== 'main' && surface !== 'floating') {
    throw new Error('Capture surface must be main or floating.')
  }
  if (pageValue !== undefined && page === undefined) throw new Error('Capture page is unsupported.')
  if (languageValue !== undefined && language === undefined) throw new Error('Capture language is unsupported.')

  return { outputPath, width, height, scaleFactor, delayMs, transcriptInput, surface, page, language }
}
