import { describe, expect, it } from 'vitest'
import type { ScutStatus } from '../src/api/contracts'
import { deriveFloatingBarPresentation } from '../src/api/floating-bar-state'

function status(overrides: Partial<ScutStatus> = {}): ScutStatus {
  return {
    protocolVersion: 1,
    mode: 'TEST',
    uptimeSeconds: 24,
    machine: {},
    whisper: {},
    audio: { state: 'IDLE' },
    android: {},
    risk: { level: 'SAFE', reason: 'Waiting for stable caller speech', source: 'SYSTEM' },
    metrics: {},
    events: [],
    ...overrides,
  }
}

describe('deriveFloatingBarPresentation', () => {
  it('stays compact and neutral when the real service is idle', () => {
    expect(deriveFloatingBarPresentation(status(), 'live')).toMatchObject({
      kind: 'resting',
      width: 196,
      height: 48,
      label: 'Local service',
      waveform: false,
    })
  })

  it('expands only for a real capturing audio state', () => {
    expect(deriveFloatingBarPresentation(status({ audio: { state: 'CAPTURING' } }), 'live')).toMatchObject({
      kind: 'listening',
      width: 332,
      height: 58,
      label: 'Listening',
      waveform: true,
      showElapsed: true,
    })
  })

  it('compresses the voice signal while a final transcript is being analysed', () => {
    expect(deriveFloatingBarPresentation(status({ audio: { state: 'FINAL_TRANSCRIPT' } }), 'live')).toMatchObject({
      kind: 'analysing',
      label: 'Analysing final speech',
      waveform: true,
      showElapsed: false,
    })
  })

  it('shows a risk affordance only for an actual non-safe backend decision', () => {
    expect(deriveFloatingBarPresentation(status({
      risk: { level: 'CRITICAL', reason: 'OTP_REQUESTED', source: 'HYBRID_BRAIN_V1' },
    }), 'live')).toMatchObject({
      kind: 'risk',
      label: 'Critical signal',
      actionLabel: 'Open SCUT',
      waveform: false,
    })
  })

  it('prioritizes real reconnect and capture error states without inventing activity', () => {
    expect(deriveFloatingBarPresentation(status({ audio: { state: 'CAPTURING' } }), 'reconnecting')).toMatchObject({
      kind: 'reconnecting',
      label: 'Reconnecting local service',
      waveform: false,
    })
    expect(deriveFloatingBarPresentation(status({ audio: { state: 'GUARDED_CAPTURE_FAILED_3' } }), 'live')).toMatchObject({
      kind: 'error',
      label: 'Capture needs attention',
      detail: 'GUARDED_CAPTURE_FAILED_3',
      waveform: false,
    })
  })
})
