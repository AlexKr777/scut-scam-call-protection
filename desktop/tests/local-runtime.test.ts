import { describe, expect, it } from 'vitest'
import { resolveLocalRuntimeDirectory } from '../electron/local-runtime'

describe('resolveLocalRuntimeDirectory', () => {
  it('uses LOCALAPPDATA and keeps production mutable state out of Program Files', () => {
    expect(resolveLocalRuntimeDirectory({ LOCALAPPDATA: 'C:\\Users\\Jane\\AppData\\Local' }, 'C:\\Program Files\\SCUT')).toBe(
      'C:\\Users\\Jane\\AppData\\Local\\SCUT',
    )
  })

  it('uses the supplied fallback when LOCALAPPDATA is unavailable', () => {
    expect(resolveLocalRuntimeDirectory({}, 'C:\\Users\\Jane\\AppData\\Roaming')).toBe(
      'C:\\Users\\Jane\\AppData\\Roaming\\SCUT',
    )
  })
})
