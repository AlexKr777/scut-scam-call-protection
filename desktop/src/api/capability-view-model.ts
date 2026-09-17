import type { ScutStatus } from './contracts'

export interface PermissionStatus {
  label: string
  value: string
}

export interface AndroidCompanionView {
  status: 'Connected' | 'Offline'
  detail: string
  device?: string
  permissions: PermissionStatus[]
}

function permissionValue(value: unknown, positive: string, negative: string): string {
  return value === true ? positive : negative
}

export function deriveAndroidCompanion(status: ScutStatus): AndroidCompanionView {
  if (status.android.status?.toUpperCase() !== 'CONNECTED') {
    return {
      status: 'Offline',
      detail: 'No paired Android companion is connected right now.',
      permissions: [],
    }
  }

  const device = status.android.devices?.[0]
  const permissions = device?.permissions ?? {}
  return {
    status: 'Connected',
    detail: device?.device ? 'The companion is reporting its latest heartbeat.' : 'A paired companion is reporting its latest heartbeat.',
    device: device?.device,
    permissions: [
      { label: 'Notifications', value: permissionValue(permissions.notifications, 'Granted', 'Needs permission') },
      { label: 'Safety overlay', value: permissionValue(permissions.overlay, 'Granted', 'Needs permission') },
      ...(typeof permissions.vibration === 'boolean'
        ? [{ label: 'Vibration', value: permissionValue(permissions.vibration, 'Available', 'Unavailable') }]
        : []),
    ],
  }
}

export function deriveCapabilityEmpty(page: 'History' | 'Alerts'): { heading: string; detail: string } {
  return page === 'History'
    ? {
        heading: 'Nothing stored yet',
        detail: 'SCUT does not currently persist conversation history on this device.',
      }
    : {
        heading: 'No alert archive',
        detail: 'SCUT can emit live alerts, but this backend does not retain an alert history.',
      }
}
