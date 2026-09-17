import { describe, expect, it } from 'vitest'
import {
  emptyLiveTranscript,
  reduceLiveTranscript,
  toLiveSocketEvent,
} from '../src/api/live-event-reducer'

const dangerousText = 'Please move the money to a safe account and tell me the verification code.'

const decisionMessage = {
  type: 'decision',
  status: { transcript: dangerousText },
  decision: {
    accepted: true,
    risk: 'CRITICAL',
    reason: 'MONEY_TRANSFER_REQUESTED',
    source: 'HYBRID_BRAIN_V1',
    riskEvent: {
      level: 'CRITICAL',
      reasons: ['CREDENTIAL_REQUEST', 'MONEY_TRANSFER_REQUEST'],
      warning: 'Possible scam: do not share money, credentials, or remote access.',
      provider_status: 'UNAVAILABLE',
      presentation_severity: 'RED',
    },
    hybrid: {
      risk_score: 90,
      requested_actions: ['REQUEST_OTP', 'REQUEST_SAFE_ACCOUNT_TRANSFER'],
      evidence: [
        {
          code: 'REQUEST_OTP',
          confidence: 0.98,
          original_span: 'tell me the verification code',
          explanation_code: 'OTP_REQUESTED',
        },
      ],
    },
  },
}

describe('live transcript event reducer', () => {
  it('attaches actual decision evidence to the current real status transcript', () => {
    const event = toLiveSocketEvent(decisionMessage)
    expect(event).not.toBeNull()

    const state = reduceLiveTranscript(emptyLiveTranscript(), event!)

    expect(state.lines).toHaveLength(1)
    expect(state.lines[0]).toMatchObject({
      text: dangerousText,
      speaker: 'CALLER',
      decision: {
        level: 'CRITICAL',
        reason: 'MONEY_TRANSFER_REQUESTED',
        score: 90,
        evidence: [{ code: 'REQUEST_OTP', originalSpan: 'tell me the verification code' }],
      },
    })
  })

  it('enriches the same line when FINAL_TRANSCRIPT arrives after the decision', () => {
    const afterDecision = reduceLiveTranscript(
      emptyLiveTranscript(),
      toLiveSocketEvent(decisionMessage)!,
    )
    const state = reduceLiveTranscript(afterDecision, toLiveSocketEvent({
      type: 'FINAL_TRANSCRIPT',
      speaker: 'CALLER',
      text: dangerousText,
      audioStartMs: 2400,
      audioEndMs: 6800,
    })!)

    expect(state.lines).toHaveLength(1)
    expect(state.lines[0]).toMatchObject({ audioStartMs: 2400, audioEndMs: 6800 })
    expect(state.lines[0].decision?.level).toBe('CRITICAL')
  })

  it('records an Android alert only after the backend emits the alert event', () => {
    const state = reduceLiveTranscript(emptyLiveTranscript(), toLiveSocketEvent({
      type: 'alert',
      id: 'alert-7',
      risk: 'CRITICAL',
      message: 'Possible scam warning sent.',
      source: 'HYBRID_BRAIN_V1',
    })!)

    expect(state.latestAlert).toEqual({
      id: 'alert-7',
      message: 'Possible scam warning sent.',
      source: 'HYBRID_BRAIN_V1',
    })
  })

  it('returns to an empty transcript session when the backend returns to OFF', () => {
    const withLine = reduceLiveTranscript(emptyLiveTranscript(), toLiveSocketEvent(decisionMessage)!)
    const state = reduceLiveTranscript(withLine, toLiveSocketEvent({
      type: 'status',
      status: {
        protocolVersion: 1,
        mode: 'OFF',
        uptimeSeconds: 3,
        machine: {},
        whisper: {},
        audio: {},
        android: {},
        risk: {},
        metrics: {},
        events: [],
      },
    })!)

    expect(state).toEqual({ lines: [] })
  })

  it('rejects malformed socket payloads instead of rendering them', () => {
    expect(toLiveSocketEvent({ type: 'FINAL_TRANSCRIPT', text: 42 })).toBeNull()
    expect(toLiveSocketEvent({ type: 'decision', decision: { risk: 20 } })).toBeNull()
  })
})
