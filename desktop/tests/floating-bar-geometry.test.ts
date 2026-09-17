import { describe, expect, it } from 'vitest'
import { floatingBarBounds, isFloatingBarSize } from '../electron/floating-bar-geometry'

describe('Floating Bar geometry', () => {
  it('anchors the compact bar inside the selected display work area', () => {
    expect(floatingBarBounds(
      { x: 0, y: 0, width: 1920, height: 1040 },
      { width: 196, height: 48 },
    )).toEqual({ x: 1696, y: 964, width: 196, height: 48 })
  })

  it('keeps the expanded bar on a secondary display instead of using primary-screen coordinates', () => {
    expect(floatingBarBounds(
      { x: 1920, y: 40, width: 2560, height: 1360 },
      { width: 332, height: 58 },
    )).toEqual({ x: 4120, y: 1314, width: 332, height: 58 })
  })

  it('allows only the two designed bar sizes through the IPC boundary', () => {
    expect(isFloatingBarSize({ width: 196, height: 48 })).toBe(true)
    expect(isFloatingBarSize({ width: 332, height: 58 })).toBe(true)
    expect(isFloatingBarSize({ width: 500, height: 1 })).toBe(false)
    expect(isFloatingBarSize(null)).toBe(false)
  })
})
