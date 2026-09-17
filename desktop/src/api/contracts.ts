export type ScutMode = 'OFF' | 'TEST' | 'PROTECT'
export type HomeTone = 'safe' | 'attention' | 'neutral'

export interface ScutEvent {
  at?: string
  type?: string
  detail?: string
}

export interface ScutStatus {
  protocolVersion: number
  mode: ScutMode
  uptimeSeconds: number
  machine: {
    windows?: string
    bluetooth?: string
    phoneLink?: string
    [key: string]: unknown
  }
  whisper: {
    selfTest?: string
    device?: string
    [key: string]: unknown
  }
  audio: {
    state?: string
    strategy?: string
    source?: string
    selected?: {
      processName?: string
      [key: string]: unknown
    } | null
    [key: string]: unknown
  }
  android: {
    status?: string
    devices?: Array<{
      device?: string
      status?: string
      permissions?: Record<string, unknown>
    }>
  }
  controlPlane?: {
    state?: 'AVAILABLE' | 'DEGRADED' | 'UNAVAILABLE'
    reason?: string
    decisionEpoch?: number
    liveSession?: boolean
  }
  tailscale?: string
  anyModel?: {
    state?: string
    [key: string]: unknown
  }
  risk: {
    level?: string
    reason?: string
    source?: string
  }
  transcript?: string
  metrics: Record<string, number | null | Record<string, number>>
  events: ScutEvent[]
}

export interface BackendHealth {
  ok: boolean
  protocolVersion: number
}

export type DiagnosticName = 'capture' | 'earbuds' | 'network' | 'predemo' | 'guarded-transcription'

export interface PairingPayload {
  endpoint: string
  pairingToken: string
  expiresAt?: string
  [key: string]: unknown
}

export interface ConversationSummary {
  id: string
  protectedReceiverId?: string | null
  protectedReceiverName?: string | null
  startedAt: string
  endedAt?: string | null
  durationSeconds?: number | null
  lifecycleStatus?: string
  preview?: string | null
  attentionState?: string | null
  incidentId?: string | null
  incidentState?: string | null
}

export interface AlertSummary {
  id: string
  conversationId?: string | null
  state: string
  source?: string
  createdAt: string
  updatedAt: string
  conversationDeleted?: boolean
  conversationPreview?: string | null
}

export interface TranscriptSegment {
  id: string
  sequence: number
  text: string
  speaker?: string
  ended_at?: string
}

export interface IncidentDetail {
  id: string
  state: string
  source?: string
  created_at?: string
  updated_at?: string
  incident_evidence?: Array<{ id: string; evidence_type: string; occurred_at?: string; payload?: { text?: string; redacted?: boolean } }>
}

export interface ConversationDetail extends ConversationSummary {
  segments: TranscriptSegment[]
  incidents: IncidentDetail[]
}

export interface HistoryPage { conversations: ConversationSummary[]; nextCursor?: string | null; offline?: boolean }
export interface AlertsPage { alerts: AlertSummary[]; nextCursor?: string | null; offline?: boolean }

export interface ScutApiError {
  message: string
}

export interface HomeState {
  headline: string
  detail: string
  modeLabel: string
  modeTone: HomeTone
  captureLabel: string
  captureMessage: string
  captureTone: HomeTone
  androidLabel: string
  androidDetail: string
  androidTone: HomeTone
  lastActivity: string
  lastActivityAt?: string
}
