import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FloatingBar } from '../src/components/FloatingBar'
import type { ScutStatus } from '../src/api/contracts'

const idleStatus: ScutStatus = {
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

describe('FloatingBar', () => {
  const resizeFloatingBar = vi.fn()
  const showMainWindow = vi.fn()

  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    window.scut = {
      getHealth: vi.fn(),
      getStatus: vi.fn().mockResolvedValue(idleStatus),
      getRealtimeEndpoint: vi.fn().mockResolvedValue('ws://127.0.0.1:8765/ws'),
      resizeFloatingBar,
      showMainWindow,
      setMode: vi.fn(),
      createPairing: vi.fn(),
      runDiagnostic: vi.fn(),
      testAndroidAlert: vi.fn(),
      submitDiagnosticTranscript: vi.fn(),
      getRecordingUrl: vi.fn(),
      getHistory: vi.fn(),
      getAlerts: vi.fn(),
      getConversation: vi.fn(),
      deleteConversation: vi.fn(),
    }
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('morphs from the truthful resting state to a real risk affordance', async () => {
    const user = userEvent.setup()
    render(<FloatingBar />)

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))
    MockWebSocket.instances[0].onopen?.()
    expect(await screen.findByText('Local service')).toBeVisible()
    expect(resizeFloatingBar).toHaveBeenLastCalledWith({ width: 196, height: 48 })

    MockWebSocket.instances[0].emit({
      type: 'status',
      status: { ...idleStatus, risk: { level: 'CRITICAL', reason: 'OTP_REQUESTED', source: 'HYBRID_BRAIN_V1' } },
    })

    expect(await screen.findByText('Critical signal')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Open SCUT' }))
    expect(showMainWindow).toHaveBeenCalledOnce()
    expect(resizeFloatingBar).toHaveBeenLastCalledWith({ width: 332, height: 58 })
  })
})
