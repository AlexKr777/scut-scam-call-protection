import { useCallback, useEffect, useState } from 'react'
import { deriveHomeState } from './api/derive-home-state'
import type { BackendHealth, ScutStatus } from './api/contracts'
import { useLiveTranscript } from './api/use-live-transcript'
import { HomeIdle } from './components/HomeIdle'
import { LiveTranscript } from './components/LiveTranscript'
import { DevicesPage } from './components/DevicesPage'
import { SettingsPage } from './components/SettingsPage'
import { HistoryPage } from './components/HistoryPage'
import { AlertsPage } from './components/AlertsPage'
import { Sidebar, type PageName } from './components/Sidebar'
import { useI18n } from './i18n'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; health: BackendHealth; status: ScutStatus }
  | { kind: 'error'; message: string }

export default function App() {
  const { t } = useI18n()
  const [loadState, setLoadState] = useState<LoadState>({ kind: 'loading' })
  const requestedPage = new URLSearchParams(window.location.search).get('page')
  const [page, setPage] = useState<PageName>(requestedPage === 'History' || requestedPage === 'Alerts' || requestedPage === 'Devices' || requestedPage === 'Settings' ? requestedPage : 'Home')
  const [notice, setNotice] = useState<string>()

  const refresh = useCallback(async () => {
    try {
      const [health, status] = await Promise.all([window.scut.getHealth(), window.scut.getStatus()])
      if (!health.ok || health.protocolVersion !== 1) throw new Error(t('disconnectedTitle'))
      setLoadState({ kind: 'ready', health, status })
    } catch (error) {
      setLoadState({ kind: 'error', message: error instanceof Error ? error.message : t('disconnectedTitle') })
    }
  }, [t])

  const applyLiveStatus = useCallback((status: ScutStatus) => {
    setLoadState((current) => current.kind === 'ready' ? { ...current, status } : current)
  }, [])
  const liveTranscript = useLiveTranscript({ onStatus: applyLiveStatus })

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(refresh, 5_000)
    return () => window.clearInterval(interval)
  }, [refresh])

  useEffect(() => {
    if (loadState.kind !== 'ready' || !window.scut.notifyVisualReady || liveTranscript.connection === 'connecting') return
    let cancelled = false
    async function notifyWhenSettled() {
      await document.fonts.ready
      await Promise.allSettled(document.getAnimations().map((animation) => animation.finished))
      if (!cancelled) window.scut.notifyVisualReady?.()
    }
    void notifyWhenSettled()
    return () => { cancelled = true }
  }, [liveTranscript.connection, loadState.kind])

  const labels: Record<PageName, string> = { Home: t('home'), History: t('history'), Alerts: t('alerts'), Devices: t('devices'), Settings: t('settings') }
  return <div className="app-shell">
    <header className="titlebar"><div className="titlebar-drag-area"><span>SCUT</span><i aria-hidden="true" /><span>{page === 'Home' && liveTranscript.transcript.lines.length > 0 ? t('liveTranscript') : labels[page]}</span></div></header>
    <Sidebar activePage={page} onNavigate={setPage} />
    <main className="workspace">
      {notice && <div className="app-notice" role="status"><span>{notice}</span><button aria-label={t('dismiss')} onClick={() => setNotice(undefined)} type="button">×</button></div>}
      {loadState.kind === 'ready' && page === 'Home' && (liveTranscript.transcript.lines.length > 0
        ? <LiveTranscript connection={liveTranscript.connection} mode={loadState.status.mode} transcript={liveTranscript.transcript} />
        : <HomeIdle state={deriveHomeState(loadState.status, t)} />)}
      {loadState.kind === 'ready' && page === 'History' && <HistoryPage onNotice={setNotice} />}
      {loadState.kind === 'ready' && page === 'Alerts' && <AlertsPage />}
      {loadState.kind === 'ready' && page === 'Devices' && <DevicesPage onNotice={setNotice} status={loadState.status} />}
      {loadState.kind === 'ready' && page === 'Settings' && <SettingsPage onNotice={setNotice} onStatus={applyLiveStatus} status={loadState.status} />}
      {loadState.kind === 'loading' && <section className="service-state" aria-live="polite"><span className="service-state-rule" /><h1>{t('loadingTitle')}</h1><span>{t('loadingBody')}</span></section>}
      {loadState.kind === 'error' && <section className="service-state" aria-live="assertive"><span className="service-state-rule tone-attention" /><h1>{t('disconnectedTitle')}</h1><span>{loadState.message}</span><button onClick={() => void refresh()} type="button">{t('retry')}</button></section>}
    </main>
  </div>
}
