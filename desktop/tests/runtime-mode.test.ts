import { describe, expect, it } from 'vitest'
import { useDevelopmentRenderer } from '../electron/runtime-mode'

describe('useDevelopmentRenderer', () => {
  it('loads the bundled renderer for a normal unpackaged Electron run', () => {
    expect(useDevelopmentRenderer(['electron', '.'])).toBe(false)
  })

  it('uses Vite only when the desktop process explicitly opts into development', () => {
    expect(useDevelopmentRenderer(['electron', '.', '--dev'])).toBe(true)
  })
})
