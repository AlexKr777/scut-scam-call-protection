import { describe, expect, it } from 'vitest'
import { parseCaptureOptions } from '../electron/capture-options'

describe('parseCaptureOptions', () => {
  it('does not enter capture mode without an output path', () => {
    expect(parseCaptureOptions(['electron', '.'])).toBeUndefined()
  })

  it('parses a bounded logical viewport and Windows scale factor', () => {
    expect(parseCaptureOptions([
      'electron',
      '.',
      '--capture-output=D:\\SCUT\\gate-a.png',
      '--capture-width=1536',
      '--capture-height=864',
      '--capture-scale=1.25',
      '--capture-delay-ms=4000',
      '--capture-transcript=Read the verification code to me.',
    ])).toEqual({
      outputPath: 'D:\\SCUT\\gate-a.png',
      width: 1536,
      height: 864,
      scaleFactor: 1.25,
      delayMs: 4000,
      transcriptInput: 'Read the verification code to me.',
      surface: 'main',
    })
  })

  it('rejects dimensions below the supported desktop minimum', () => {
    expect(() => parseCaptureOptions([
      'electron',
      '.',
      '--capture-output=gate-a.png',
      '--capture-width=800',
      '--capture-height=600',
    ])).toThrow('Capture viewport')
  })

  it('allows the designed Floating Bar capture dimensions only for the floating surface', () => {
    expect(parseCaptureOptions([
      'electron',
      '.',
      '--capture-output=gate-c-bar.png',
      '--capture-surface=floating',
      '--capture-width=332',
      '--capture-height=58',
    ])).toMatchObject({ width: 332, height: 58, surface: 'floating' })
  })
})
