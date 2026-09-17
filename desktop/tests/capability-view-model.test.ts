import { describe, expect, it } from 'vitest'
import { deriveAndroidCompanion, deriveCapabilityEmpty } from '../src/api/capability-view-model'
import type { ScutStatus } from '../src/api/contracts'

const offline: ScutStatus = {
  protocolVersion: 1,
  mode: 'OFF',
  uptimeSeconds: 1,
  machine: {}, whisper: {}, audio: {},
  android: { status: 'OFFLINE', devices: [] },
  risk: {}, metrics: {}, events: [],
}

describe('capability view models', () => {
  it('does not call an offline Android companion paired or permission-ready', () => {
    expect(deriveAndroidCompanion(offline)).toMatchObject({
      status: 'Offline',
      detail: 'No paired Android companion is connected right now.',
      permissions: [],
    })
  })

  it('uses only connected device heartbeat permissions when the backend supplies them', () => {
    expect(deriveAndroidCompanion({
      ...offline,
      android: { status: 'CONNECTED', devices: [{ device: 'Pixel 9', permissions: { notifications: true, overlay: false } }] },
    })).toMatchObject({
      status: 'Connected',
      device: 'Pixel 9',
      permissions: [
        { label: 'Notifications', value: 'Granted' },
        { label: 'Safety overlay', value: 'Needs permission' },
      ],
    })
  })

  it('marks history and alerts as unavailable rather than creating placeholder records', () => {
    expect(deriveCapabilityEmpty('History')).toEqual({
      heading: 'Nothing stored yet',
      detail: 'SCUT does not currently persist conversation history on this device.',
    })
    expect(deriveCapabilityEmpty('Alerts')).toEqual({
      heading: 'No alert archive',
      detail: 'SCUT can emit live alerts, but this backend does not retain an alert history.',
    })
  })
})
