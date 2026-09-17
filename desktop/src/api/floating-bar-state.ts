import type { ScutStatus } from './contracts'
import type { StreamConnection } from './use-live-transcript'

export type FloatingBarKind = 'resting' | 'listening' | 'analysing' | 'risk' | 'error' | 'reconnecting'

export interface FloatingBarPresentation {
  kind: FloatingBarKind
  width: 196 | 332
  height: 48 | 58
  label: string
  detail?: string
  waveform: boolean
  showElapsed: boolean
  actionLabel?: 'Open SCUT'
  riskLevel?: string
}

const COMPACT_SIZE = { width: 196, height: 48 } as const
const EXPANDED_SIZE = { width: 332, height: 58 } as const

function isCaptureError(audioState: string): boolean {
  return audioState === 'ERROR'
    || audioState.includes('FAILED')
    || audioState.includes('ERROR')
    || audioState === 'TEST_MODE_REQUIRED'
}

function isRisk(level: string | undefined): boolean {
  return level === 'SUSPICIOUS' || level === 'HIGH_RISK' || level === 'CRITICAL' || level === 'WATCH'
}

export function deriveFloatingBarPresentation(
  status: ScutStatus | undefined,
  connection: StreamConnection,
): FloatingBarPresentation {
  if (connection !== 'live') {
    return {
      kind: 'reconnecting',
      ...COMPACT_SIZE,
      label: connection === 'connecting' ? 'Connecting local service' : 'Reconnecting local service',
      waveform: false,
      showElapsed: false,
    }
  }

  const riskLevel = status?.risk.level
  if (isRisk(riskLevel)) {
    return {
      kind: 'risk',
      ...EXPANDED_SIZE,
      label: riskLevel === 'CRITICAL' ? 'Critical signal' : 'Risk signal',
      detail: status?.risk.reason,
      waveform: false,
      showElapsed: false,
      actionLabel: 'Open SCUT',
      riskLevel,
    }
  }

  const audioState = status?.audio.state ?? 'IDLE'
  if (isCaptureError(audioState)) {
    return {
      kind: 'error',
      ...EXPANDED_SIZE,
      label: 'Capture needs attention',
      detail: audioState,
      waveform: false,
      showElapsed: false,
    }
  }

  if (audioState === 'STARTING' || audioState === 'CAPTURING') {
    return {
      kind: 'listening',
      ...EXPANDED_SIZE,
      label: 'Listening',
      detail: audioState === 'CAPTURING' ? 'Capturing audio' : 'Starting audio capture',
      waveform: true,
      showElapsed: true,
    }
  }

  if (audioState === 'FINAL_TRANSCRIPT' || audioState === 'FAST_PARTIAL' || audioState === 'STABLE_TRANSCRIPT') {
    return {
      kind: 'analysing',
      ...EXPANDED_SIZE,
      label: 'Analysing final speech',
      detail: audioState,
      waveform: true,
      showElapsed: false,
    }
  }

  return {
    kind: 'resting',
    ...COMPACT_SIZE,
    label: 'Local service',
    detail: `Protection / ${status?.mode.toLowerCase() ?? 'unavailable'}`,
    waveform: false,
    showElapsed: false,
  }
}
