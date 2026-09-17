import type { HomeState, HomeTone, ScutEvent, ScutStatus } from './contracts'
import type { Translator } from '../i18n'

const MODE_COPY: Record<
  ScutStatus['mode'],
  Pick<HomeState, 'headline' | 'detail' | 'modeLabel' | 'modeTone'>
> = {
  OFF: {
    headline: 'Protection is paused',
    detail: "SCUT is open, but it isn't evaluating caller speech while protection is off.",
    modeLabel: 'Off',
    modeTone: 'neutral',
  },
  TEST: {
    headline: 'Test mode is ready',
    detail: 'SCUT is available for explicit diagnostics. No continuous call protection is running.',
    modeLabel: 'Test',
    modeTone: 'attention',
  },
  PROTECT: {
    headline: 'Protection mode is on',
    detail: 'SCUT will evaluate stable caller speech it receives. Capture readiness is shown separately below.',
    modeLabel: 'Protect',
    modeTone: 'safe',
  },
}

function sentenceCase(value: string): string {
  const normalized = value.trim().replaceAll('_', ' ').toLowerCase()
  return normalized ? normalized[0].toUpperCase() + normalized.slice(1) : 'Activity'
}

function deriveActivity(events: ScutEvent[]): Pick<HomeState, 'lastActivity' | 'lastActivityAt'> {
  const event = events.at(-1)
  if (!event) return { lastActivity: 'No recent activity' }

  const label = sentenceCase(event.type ?? '')
  const detail = event.detail?.trim()
  return {
    lastActivity: detail ? `${label} · ${detail}` : label,
    lastActivityAt: event.at,
  }
}

function deriveCapture(status: ScutStatus): Pick<
  HomeState,
  'captureLabel' | 'captureMessage' | 'captureTone'
> {
  const state = status.audio.state?.toUpperCase()
  const selected = status.audio.selected?.processName?.trim()

  if (state === 'PASS' && selected) {
    return {
      captureLabel: 'Capture verified',
      captureMessage: `Phone Link audio was verified with ${selected}.`,
      captureTone: 'safe',
    }
  }
  if (state === 'FAIL') {
    return {
      captureLabel: 'Capture needs attention',
      captureMessage: 'The latest Phone Link capture check did not pass on this machine.',
      captureTone: 'attention',
    }
  }
  return {
    captureLabel: 'Capture unverified',
    captureMessage: 'Phone Link capture has not been verified on this machine.',
    captureTone: 'attention',
  }
}

function deriveAndroid(status: ScutStatus): Pick<
  HomeState,
  'androidLabel' | 'androidDetail' | 'androidTone'
> {
  const connected = status.android.status?.toUpperCase() === 'CONNECTED'
  if (!connected) {
    return {
      androidLabel: 'Android companion offline',
      androidDetail: 'No paired companion is connected right now.',
      androidTone: 'neutral',
    }
  }

  const device = status.android.devices?.[0]?.device?.trim()
  return {
    androidLabel: 'Android companion connected',
    androidDetail: device ? `${device} is responding to SCUT.` : 'A paired companion is responding to SCUT.',
    androidTone: 'safe',
  }
}

export function deriveHomeState(status: ScutStatus, t?: Translator): HomeState {
  const state: HomeState = {
    ...MODE_COPY[status.mode],
    ...deriveCapture(status),
    ...deriveAndroid(status),
    ...deriveActivity(status.events),
  }
  if (!t) return state
  const mode = status.mode === 'OFF'
    ? { headline: t('protectionPaused'), detail: t('protectionPausedBody'), modeLabel: t('modeOff') }
    : status.mode === 'TEST'
      ? { headline: t('testReady'), detail: t('testReadyBody'), modeLabel: t('modeTest') }
      : { headline: t('protectionOn'), detail: t('protectionOnBody'), modeLabel: t('modeProtect') }
  const audio = status.audio.state?.toUpperCase()
  if (audio === 'PASS' && status.audio.selected?.processName) {
    state.captureLabel = t('captureVerified'); state.captureMessage = t('captureVerifiedBody', { value: status.audio.selected.processName })
  } else if (audio === 'FAIL') {
    state.captureLabel = t('captureAttention'); state.captureMessage = t('captureAttentionBody')
  } else {
    state.captureLabel = t('captureUnverified'); state.captureMessage = t('captureUnverifiedBody')
  }
  if (status.android.status?.toUpperCase() === 'CONNECTED') {
    state.androidLabel = t('companionConnected')
    state.androidDetail = t('companionConnectedBody', { value: status.android.devices?.[0]?.device?.trim() || t('unknownPhone') })
  } else {
    state.androidLabel = t('companionOffline'); state.androidDetail = t('companionOfflineBody')
  }
  if (status.events.length === 0) state.lastActivity = t('noRecent')
  return { ...state, ...mode }
}

export function isHomeTone(value: string): value is HomeTone {
  return value === 'safe' || value === 'attention' || value === 'neutral'
}
