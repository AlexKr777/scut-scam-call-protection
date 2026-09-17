import { describe, expect, it } from 'vitest'
import { deriveHomeState } from '../src/api/derive-home-state'
import type { ScutStatus } from '../src/api/contracts'

const offStatus: ScutStatus = {
  protocolVersion: 1,
  mode: 'OFF',
  uptimeSeconds: 4.2,
  machine: {
    windows: 'Windows 11',
    bluetooth: 'AVAILABLE',
    phoneLink: 'DETECTED',
  },
  whisper: { selfTest: 'PASS', device: 'cuda' },
  audio: { state: 'IDLE', strategy: 'NOT TESTED', source: '-' },
  android: { status: 'OFFLINE', devices: [] },
  tailscale: 'NOT INSTALLED',
  anyModel: { state: 'NOT CONFIGURED' },
  risk: { level: 'SAFE', reason: 'Protection off', source: 'SYSTEM' },
  transcript: '-',
  metrics: { sttMs: null, localDecisionMs: null, alertDeliveryMs: null },
  events: [],
}

describe('deriveHomeState', () => {
  it('states plainly when protection is off', () => {
    expect(deriveHomeState(offStatus).headline).toBe('Protection is paused')
    expect(deriveHomeState(offStatus).detail).toBe(
      "SCUT is open, but it isn't evaluating caller speech while protection is off.",
    )
  })

  it('does not turn an unverified Phone Link probe into a protection claim', () => {
    expect(deriveHomeState(offStatus).captureMessage).toBe(
      'Phone Link capture has not been verified on this machine.',
    )
    expect(deriveHomeState(offStatus).captureTone).toBe('attention')
  })

  it('uses only a real event for last activity', () => {
    expect(deriveHomeState(offStatus).lastActivity).toBe('No recent activity')

    const withEvent: ScutStatus = {
      ...offStatus,
      events: [{ at: '16:04:12', type: 'CAPTURE', detail: 'FAIL: NO_PHONE_LINK_CANDIDATES' }],
    }
    expect(deriveHomeState(withEvent).lastActivity).toBe('Capture · FAIL: NO_PHONE_LINK_CANDIDATES')
    expect(deriveHomeState(withEvent).lastActivityAt).toBe('16:04:12')
  })

  it('reports the Android connection without inventing delivery state', () => {
    expect(deriveHomeState(offStatus).androidLabel).toBe('Android companion offline')
    expect(deriveHomeState(offStatus).androidDetail).toBe('No paired companion is connected right now.')
  })
})
