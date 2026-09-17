export function useDevelopmentRenderer(argv: readonly string[]): boolean {
  return argv.includes('--dev')
}
