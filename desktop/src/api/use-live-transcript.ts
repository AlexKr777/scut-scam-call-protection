import { useEffect, useState } from 'react'
import type { ScutStatus } from './contracts'
import {
  emptyLiveTranscript,
  reduceLiveTranscript,
  toLiveSocketEvent,
  type LiveTranscriptState,
} from './live-event-reducer'

export type StreamConnection = 'connecting' | 'live' | 'reconnecting' | 'unavailable'

interface UseLiveTranscriptOptions {
  onStatus(status: ScutStatus): void
}

export function useLiveTranscript({ onStatus }: UseLiveTranscriptOptions): {
  transcript: LiveTranscriptState
  connection: StreamConnection
} {
  const [transcript, setTranscript] = useState<LiveTranscriptState>(emptyLiveTranscript)
  const [connection, setConnection] = useState<StreamConnection>('connecting')

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | undefined
    let reconnectTimer: number | undefined

    const connect = async () => {
      try {
        const endpoint = await window.scut.getRealtimeEndpoint()
        if (cancelled) return

        socket = new WebSocket(endpoint)
        socket.onopen = () => {
          setConnection('live')
          socket?.send(JSON.stringify({ type: 'subscribe' }))
        }
        socket.onmessage = (message) => {
          try {
            const event = toLiveSocketEvent(JSON.parse(message.data))
            if (!event) return
            if (event.type === 'status') onStatus(event.status)
            if (event.type === 'decision' && event.status) onStatus(event.status)
            setTranscript((current) => reduceLiveTranscript(current, event))
          } catch {
            // The local socket can close/reconnect; malformed frames never reach UI state.
          }
        }
        socket.onerror = () => socket?.close()
        socket.onclose = () => {
          if (cancelled) return
          setConnection('reconnecting')
          reconnectTimer = window.setTimeout(() => void connect(), 1_500)
        }
      } catch {
        if (cancelled) return
        setConnection('unavailable')
        reconnectTimer = window.setTimeout(() => void connect(), 3_000)
      }
    }

    void connect()
    return () => {
      cancelled = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [onStatus])

  return { transcript, connection }
}
