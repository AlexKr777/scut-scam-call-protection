import { useEffect, useRef, useState } from 'react'
import { deriveFloatingBarPresentation, type FloatingBarKind } from '../api/floating-bar-state'
import { useFloatingBarStatus } from '../api/use-floating-bar-status'
import { useI18n } from '../i18n'

function useObservedElapsed(active: boolean): number {
  const startedAt = useRef<number | undefined>(undefined)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!active) {
      startedAt.current = undefined
      setElapsed(0)
      return
    }

    startedAt.current ??= Date.now()
    const update = () => setElapsed(Math.floor((Date.now() - startedAt.current!) / 1_000))
    update()
    const timer = window.setInterval(update, 1_000)
    return () => window.clearInterval(timer)
  }, [active])

  return elapsed
}

function elapsedLabel(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function VoiceWaveform({ kind }: { kind: FloatingBarKind }) {
  return (
    <span aria-hidden="true" className={`voice-waveform is-${kind}`}>
      <i /><i /><i /><i /><i />
    </span>
  )
}

export function FloatingBar() {
  const { t } = useI18n()
  const { status, connection } = useFloatingBarStatus()
  const presentation = deriveFloatingBarPresentation(status, connection)
  const elapsed = useObservedElapsed(presentation.showElapsed)
  const notifiedReady = useRef(false)
  const label = presentation.kind === 'reconnecting' ? (connection === 'connecting' ? t('connectingService') : t('reconnectingService'))
    : presentation.kind === 'risk' ? (presentation.riskLevel === 'CRITICAL' ? t('criticalSignal') : t('riskSignal'))
      : presentation.kind === 'error' ? t('captureAttention')
        : presentation.kind === 'listening' ? t('listening')
          : presentation.kind === 'analysing' ? t('analysing') : t('localService')

  useEffect(() => {
    document.body.classList.add('floating-body')
    document.title = 'SCUT Voice Bar'
    return () => document.body.classList.remove('floating-body')
  }, [])

  useEffect(() => {
    void window.scut.resizeFloatingBar?.({ width: presentation.width, height: presentation.height })
  }, [presentation.height, presentation.width])

  useEffect(() => {
    if (notifiedReady.current || !status || connection === 'connecting') return
    notifiedReady.current = true
    window.scut.notifyFloatingBarReady?.()
  }, [connection, status])

  return (
    <section
      aria-label="SCUT Floating Bar"
      className={`floating-bar is-${presentation.kind}${presentation.riskLevel ? ` risk-${presentation.riskLevel.toLowerCase()}` : ''}`}
    >
      <div className="floating-bar-content" aria-live="polite">
        <span className="floating-status-dot" aria-hidden="true" />
        {presentation.waveform && <VoiceWaveform kind={presentation.kind} />}
        <div className="floating-copy">
          <strong>{label}</strong>
          {presentation.showElapsed
            ? <span>{t('listeningElapsed', { value: elapsedLabel(elapsed) })}</span>
            : presentation.detail && <span>{presentation.detail}</span>}
        </div>
        {presentation.actionLabel && <button
          className="floating-open-main"
          onClick={() => void window.scut.showMainWindow?.()}
          type="button"
        >
          {t('openScut')}
        </button>}
      </div>
    </section>
  )
}
