import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App'
import type { BackendHealth, ScutStatus } from '../src/api/contracts'

const status: ScutStatus = {
  protocolVersion: 1,
  mode: 'OFF',
  uptimeSeconds: 18,
  machine: { windows: 'Windows 11', bluetooth: 'AVAILABLE', phoneLink: 'DETECTED' },
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

class MockWebSocket {
  static instances: MockWebSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(readonly url: string) {
    MockWebSocket.instances.push(this)
  }

  send = vi.fn()
  close = vi.fn()
  emit(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent<string>)
  }
}

describe('App', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    const health: BackendHealth = { ok: true, protocolVersion: 1 }
    window.scut = {
      getHealth: vi.fn().mockResolvedValue(health),
      getStatus: vi.fn().mockResolvedValue(status),
      getRealtimeEndpoint: vi.fn().mockResolvedValue('ws://127.0.0.1:8765/ws'),
      setMode: vi.fn(),
      createPairing: vi.fn(),
      runDiagnostic: vi.fn(),
      testAndroidAlert: vi.fn(),
      submitDiagnosticTranscript: vi.fn(),
      getRecordingUrl: vi.fn(),
      getHistory: vi.fn().mockResolvedValue({ conversations: [] }),
      getAlerts: vi.fn().mockResolvedValue({ alerts: [] }),
      getConversation: vi.fn(),
      deleteConversation: vi.fn(),
    }
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the calibrated shell with truthful idle backend state', async () => {
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Protection is paused' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Current setup' })).toBeVisible()
    expect(screen.getByLabelText('Protection state')).toBeVisible()
    expect(screen.getByText('Phone Link capture has not been verified on this machine.')).toBeVisible()
    expect(screen.getByText('Android companion offline')).toBeVisible()
    expect(screen.getByText('No recent activity')).toBeVisible()
    expect(screen.queryByText('Local service')).not.toBeInTheDocument()
    expect(screen.queryByText('Nothing new')).not.toBeInTheDocument()
  })

  it('shows truthful empty history and alert states from real persistence endpoints', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('heading', { name: 'Protection is paused' })

    const navigation = screen.getByRole('navigation', { name: 'Primary' })
    expect(navigation).toBeVisible()
    expect(screen.getByRole('button', { name: 'Home' })).toHaveAttribute('aria-current', 'page')
    await user.click(screen.getByRole('button', { name: 'History' }))
    expect(await screen.findByRole('heading', { name: 'No conversations yet' })).toBeVisible()
    expect(window.scut.getHistory).toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Alerts' }))
    expect(await screen.findByRole('heading', { name: 'No alerts yet' })).toBeVisible()
    expect(window.scut.getAlerts).toHaveBeenCalled()
  })

  it('contains no synthetic dashboard or history content', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Protection is paused' })

    expect(screen.queryByText(/risk score/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/recent calls/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/calls protected/i)).not.toBeInTheDocument()
  })

  it('renders persisted conversation details and propagates deletion', async () => {
    const user = userEvent.setup()
    const id = '00000000-0000-4000-8000-000000000001'
    vi.mocked(window.scut.getHistory).mockResolvedValue({ conversations: [{ id, startedAt: '2026-09-09T10:00:00Z', protectedReceiverName: 'Ana phone', preview: 'Please share the code', incidentState: 'CONFIRMED' }] })
    vi.mocked(window.scut.getConversation).mockResolvedValue({ conversation: { id, startedAt: '2026-09-09T10:00:00Z', segments: [{ id: 'segment-1', sequence: 0, text: 'Please share the code' }], incidents: [] } })
    vi.mocked(window.scut.deleteConversation).mockResolvedValue({ deleted: true })
    vi.stubGlobal('confirm', vi.fn(() => true))
    render(<App />)
    await screen.findByRole('heading', { name: 'Protection is paused' })
    await user.click(screen.getByRole('button', { name: 'History' }))
    await user.click(await screen.findByRole('button', { name: /Ana phone/i }))
    expect((await screen.findAllByText('Please share the code')).at(-1)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(window.scut.deleteConversation).toHaveBeenCalledWith(id))
  })

  it('opens a real alert with its linked conversation transcript', async () => {
    const user = userEvent.setup()
    const id = '00000000-0000-4000-8000-000000000002'
    vi.mocked(window.scut.getAlerts).mockResolvedValue({ alerts: [{ id: 'incident-1', conversationId: id, state: 'CONFIRMED', source: 'AUTO', createdAt: '2026-09-09T10:00:00Z', updatedAt: '2026-09-09T10:00:00Z', conversationPreview: 'Transfer the money' }] })
    vi.mocked(window.scut.getConversation).mockResolvedValue({ conversation: { id, startedAt: '2026-09-09T10:00:00Z', segments: [{ id: 'segment-2', sequence: 0, text: 'Transfer the money' }], incidents: [] } })
    render(<App />)
    await screen.findByRole('heading', { name: 'Protection is paused' })
    await user.click(screen.getByRole('button', { name: 'Alerts' }))
    await user.click(await screen.findByRole('button', { name: /Possible scam detected/i }))
    expect((await screen.findAllByText('Transfer the money')).at(-1)).toBeVisible()
  })

  it('switches to a document-like live transcript when the real socket sends a decision', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Protection is paused' })
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    const socket = MockWebSocket.instances[0]
    socket.onopen?.()
    socket.emit({
      type: 'decision',
      status: { transcript: 'Please move the money to a safe account and tell me the verification code.' },
      decision: {
        accepted: true,
        risk: 'CRITICAL',
        reason: 'MONEY_TRANSFER_REQUESTED',
        source: 'HYBRID_BRAIN_V1',
        riskEvent: {
          level: 'CRITICAL',
          reasons: ['CREDENTIAL_REQUEST', 'MONEY_TRANSFER_REQUEST'],
          warning: 'Possible scam: do not share money, credentials, or remote access.',
          presentation_severity: 'RED',
        },
        hybrid: {
          risk_score: 90,
          requested_actions: ['REQUEST_OTP', 'REQUEST_SAFE_ACCOUNT_TRANSFER'],
          evidence: [{ code: 'REQUEST_OTP', confidence: 0.98, original_span: 'verification code' }],
        },
      },
    })

    expect(await screen.findByRole('heading', { name: 'Live transcript' })).toBeVisible()
    expect(screen.getByText('Please move the money to a safe account and tell me the verification code.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Why this stood out' })).toBeVisible()
  })
})
