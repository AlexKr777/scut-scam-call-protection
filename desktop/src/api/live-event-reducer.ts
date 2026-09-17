import type { ScutMode, ScutStatus } from './contracts'

export type TranscriptRiskLevel = 'SAFE' | 'SUSPICIOUS' | 'CRITICAL' | 'HIGH_RISK' | 'WATCH'

export interface TranscriptEvidence {
  code: string
  confidence?: number
  originalSpan?: string
  explanationCode?: string
}

export interface TranscriptDecision {
  level: TranscriptRiskLevel
  reason: string
  source: string
  score?: number
  requestedActions: string[]
  evidence: TranscriptEvidence[]
  reasons: string[]
  warning?: string
  presentationSeverity?: string
  providerStatus?: string
}

export interface TranscriptLine {
  id: string
  text: string
  speaker: string
  audioStartMs?: number
  audioEndMs?: number
  decision?: TranscriptDecision
}

export interface AndroidAlert {
  id: string
  message: string
  source: string
}

interface RiskEvent {
  level: TranscriptRiskLevel
  reasons: string[]
  warning?: string
  providerStatus?: string
  presentationSeverity?: string
}

export interface LiveTranscriptState {
  lines: TranscriptLine[]
  latestAlert?: AndroidAlert
  latestRiskEvent?: RiskEvent
  pendingDecision?: TranscriptDecision
}

export type LiveSocketEvent =
  | { type: 'finalTranscript'; text: string; speaker: string; audioStartMs?: number; audioEndMs?: number }
  | { type: 'decision'; decision: TranscriptDecision; transcript?: string; status?: ScutStatus }
  | { type: 'riskEvent'; riskEvent: RiskEvent }
  | { type: 'alert'; alert: AndroidAlert }
  | { type: 'status'; status: ScutStatus }
  | { type: 'hello' }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readText(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function readNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function readStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.flatMap((item) => (typeof item === 'string' ? [item] : [])) : []
}

function isRiskLevel(value: unknown): value is TranscriptRiskLevel {
  return value === 'SAFE' || value === 'SUSPICIOUS' || value === 'CRITICAL' || value === 'HIGH_RISK' || value === 'WATCH'
}

function isScutMode(value: unknown): value is ScutMode {
  return value === 'OFF' || value === 'TEST' || value === 'PROTECT'
}

function parseRiskEvent(value: unknown): RiskEvent | undefined {
  if (!isRecord(value) || !isRiskLevel(value.level)) return undefined

  return {
    level: value.level,
    reasons: readStrings(value.reasons),
    warning: readText(value.warning),
    providerStatus: readText(value.provider_status),
    presentationSeverity: readText(value.presentation_severity),
  }
}

function parseEvidence(value: unknown): TranscriptEvidence[] {
  if (!Array.isArray(value)) return []

  return value.flatMap((item) => {
    if (!isRecord(item)) return []
    const code = readText(item.code)
    if (!code) return []
    return [{
      code,
      confidence: readNumber(item.confidence),
      originalSpan: readText(item.original_span),
      explanationCode: readText(item.explanation_code),
    }]
  })
}

function parseDecision(value: unknown): TranscriptDecision | undefined {
  if (!isRecord(value) || !isRiskLevel(value.risk)) return undefined

  const reason = readText(value.reason)
  const source = readText(value.source)
  if (!reason || !source) return undefined

  const hybrid = isRecord(value.hybrid) ? value.hybrid : {}
  const riskEvent = parseRiskEvent(value.riskEvent)
  return {
    level: value.risk,
    reason,
    source,
    score: readNumber(hybrid.risk_score),
    requestedActions: readStrings(hybrid.requested_actions),
    evidence: parseEvidence(hybrid.evidence),
    reasons: riskEvent?.reasons ?? [],
    warning: riskEvent?.warning,
    presentationSeverity: riskEvent?.presentationSeverity,
    providerStatus: riskEvent?.providerStatus,
  }
}

function isScutStatus(value: unknown): value is ScutStatus {
  if (!isRecord(value)) return false
  if (!isScutMode(value.mode)) return false

  return typeof value.protocolVersion === 'number'
    && typeof value.uptimeSeconds === 'number'
    && isRecord(value.machine)
    && isRecord(value.whisper)
    && isRecord(value.audio)
    && isRecord(value.android)
    && isRecord(value.risk)
    && isRecord(value.metrics)
    && Array.isArray(value.events)
}

export function toLiveSocketEvent(value: unknown): LiveSocketEvent | null {
  if (!isRecord(value)) return null

  switch (value.type) {
    case 'hello':
      return { type: 'hello' }
    case 'status':
      return isScutStatus(value.status) ? { type: 'status', status: value.status } : null
    case 'FINAL_TRANSCRIPT': {
      const text = readText(value.text)
      if (!text) return null
      return {
        type: 'finalTranscript',
        text,
        speaker: readText(value.speaker) ?? 'CALLER',
        audioStartMs: readNumber(value.audioStartMs),
        audioEndMs: readNumber(value.audioEndMs),
      }
    }
    case 'risk_event': {
      const riskEvent = parseRiskEvent(value.riskEvent)
      return riskEvent ? { type: 'riskEvent', riskEvent } : null
    }
    case 'decision': {
      const decision = parseDecision(value.decision)
      if (!decision) return null
      const status = isScutStatus(value.status) ? value.status : undefined
      const transcript = status ? readText(status.transcript) : (isRecord(value.status) ? readText(value.status.transcript) : undefined)
      return { type: 'decision', decision, transcript: transcript === '-' ? undefined : transcript, status }
    }
    case 'alert': {
      const id = readText(value.id)
      const message = readText(value.message)
      const source = readText(value.source)
      return id && message && source ? { type: 'alert', alert: { id, message, source } } : null
    }
    default:
      return null
  }
}

export function emptyLiveTranscript(): LiveTranscriptState {
  return { lines: [] }
}

function findMatchingLine(lines: TranscriptLine[], text: string): number {
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    if (lines[index].text === text) return index
  }
  return -1
}

function upsertLine(
  state: LiveTranscriptState,
  incoming: Omit<TranscriptLine, 'id'>,
): LiveTranscriptState {
  const match = findMatchingLine(state.lines, incoming.text)
  if (match >= 0) {
    const lines = [...state.lines]
    lines[match] = { ...lines[match], ...incoming, decision: incoming.decision ?? lines[match].decision }
    return { ...state, lines }
  }

  const id = `line-${incoming.audioStartMs ?? 'status'}-${incoming.audioEndMs ?? state.lines.length + 1}`
  return { ...state, lines: [...state.lines, { id, ...incoming }].slice(-12) }
}

export function reduceLiveTranscript(
  state: LiveTranscriptState,
  event: LiveSocketEvent,
): LiveTranscriptState {
  switch (event.type) {
    case 'riskEvent':
      return { ...state, latestRiskEvent: event.riskEvent }
    case 'alert':
      return { ...state, latestAlert: event.alert }
    case 'decision': {
      const withRisk = { ...state, latestRiskEvent: {
        level: event.decision.level,
        reasons: event.decision.reasons,
        warning: event.decision.warning,
        providerStatus: event.decision.providerStatus,
        presentationSeverity: event.decision.presentationSeverity,
      } }
      return event.transcript
        ? upsertLine(withRisk, { text: event.transcript, speaker: 'CALLER', decision: event.decision })
        : { ...withRisk, pendingDecision: event.decision }
    }
    case 'finalTranscript': {
      const next = upsertLine(state, {
        text: event.text,
        speaker: event.speaker,
        audioStartMs: event.audioStartMs,
        audioEndMs: event.audioEndMs,
        decision: state.pendingDecision,
      })
      return { ...next, pendingDecision: undefined }
    }
    case 'hello':
      return state
    case 'status':
      return event.status.mode === 'OFF' ? emptyLiveTranscript() : state
  }
}
