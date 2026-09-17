import { win32 as path } from 'node:path'

export function resolveLocalRuntimeDirectory(
  environment: NodeJS.ProcessEnv = process.env,
  fallbackAppData: string,
): string {
  return path.join(environment.LOCALAPPDATA?.trim() || fallbackAppData, 'SCUT')
}
