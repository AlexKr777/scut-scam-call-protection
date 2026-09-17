import { useEffect, useState } from 'react'
import type { ScutStatus } from './contracts'
import { toLiveSocketEvent } from './live-event-reducer'
import type { StreamConnection } from './use-live-transcript'

export function useFloatingBarStatus(): { status?: ScutStatus; connection: StreamConnection } {
  const [status, setStatus] = useState<ScutStatus>()
  const [connection, setConnection] = useState<StreamConnection>('connecting')

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | undefined
    let reconnectTimer: number | undefined

    const connect = async () => {
      try {
        const [initialStatus, endpoint] = await Promise.all([
          window.scut.getStatus(),
          window.scut.getRealtimeEndpoint(),
        ])
        if (cancelled) return
        setStatus(initialStatus)
        socket = new WebSocket(endpoint)
        socket.onopen = () => {
          setConnection('live')
          socket?.send(JSON.stringify({ type: 'subscribe' }))
        }
        socket.onmessage = (message) => {
          try {
            const event = toLiveSocketEvent(JSON.parse(message.data))
            if (event?.type === 'status') setStatus(event.status)
            if (event?.type === 'decision' && event.status) setStatus(event.status)
          } catch {
            // Malformed local frames are ignored at the typed WebSocket boundary.
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
  }, [])

  return { status, connection }
}
