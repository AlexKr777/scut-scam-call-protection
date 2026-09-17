export interface FloatingBarSize {
  width: 196 | 332
  height: 48 | 58
}

export interface DisplayWorkArea {
  x: number
  y: number
  width: number
  height: number
}

export interface FloatingBarBounds extends FloatingBarSize {
  x: number
  y: number
}

const HORIZONTAL_INSET = 28
const VERTICAL_INSET = 28

export function isFloatingBarSize(value: unknown): value is FloatingBarSize {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const size = value as Record<string, unknown>
  return (size.width === 196 && size.height === 48) || (size.width === 332 && size.height === 58)
}

export function floatingBarBounds(workArea: DisplayWorkArea, size: FloatingBarSize): FloatingBarBounds {
  return {
    x: workArea.x + workArea.width - size.width - HORIZONTAL_INSET,
    y: workArea.y + workArea.height - size.height - VERTICAL_INSET,
    ...size,
  }
}
