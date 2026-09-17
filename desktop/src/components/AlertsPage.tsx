import { useEffect, useState } from 'react'
import type { AlertSummary, ConversationDetail } from '../api/contracts'
import { useI18n } from '../i18n'

function when(value: string, language: string): string {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? '' : new Intl.DateTimeFormat(language, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function AlertsPage() {
  const { language, t } = useI18n()
  const [items, setItems] = useState<AlertSummary[]>([])
  const [cursor, setCursor] = useState<string>()
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [offline, setOffline] = useState(false)
  const [selected, setSelected] = useState<AlertSummary>()
  const [conversation, setConversation] = useState<ConversationDetail>()

  async function load(next?: string) {
    setState('loading')
    try { const page = await window.scut.getAlerts(next); setItems((current) => next ? [...current, ...page.alerts] : page.alerts); setCursor(page.nextCursor ?? undefined); setOffline(Boolean(page.offline)); setState('ready') } catch { setState('error') }
  }
  useEffect(() => { void load() }, [])
  useEffect(() => {
    setConversation(undefined)
    if (!selected?.conversationId || selected.conversationDeleted) return
    let active = true
    window.scut.getConversation(selected.conversationId).then((value) => { if (active) setConversation(value.conversation) }).catch(() => undefined)
    return () => { active = false }
  }, [selected])

  return <section className="capability-page archive-page" aria-labelledby="alerts-heading">
    <header className="page-toolbar"><span>{t('alerts')}</span><small>{items.length}</small></header>
    <div className="page-heading"><span>{t('alertsEyebrow')}</span><h1 id="alerts-heading">{t('alertsTitle')}</h1><p>{t('alertsBody')}</p></div>
    {offline && <p className="archive-banner">{t('offlineCached')}</p>}
    {state === 'loading' && items.length === 0 && <div className="archive-state">{t('loading')}</div>}
    {state === 'error' && <div className="archive-state"><p>{t('unavailable')}</p><button onClick={() => void load()} type="button">{t('retry')}</button></div>}
    {state === 'ready' && items.length === 0 && <div className="archive-empty"><h2>{t('alertsEmpty')}</h2><p>{t('alertsEmptyBody')}</p></div>}
    <ol className="archive-list alerts-list">{items.map((item, index) => { const cleared = item.state === 'CLEARED' || item.state === 'USER_DISMISSED'; return <li key={item.id} style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}><button onClick={() => setSelected(item)} type="button"><div><time>{when(item.updatedAt, language)}</time><strong>{cleared ? t('alertCleared') : t('possibleScam')}</strong><p>{item.conversationPreview || t('contextLimited')}</p></div><span className={cleared ? '' : 'attention-mark'}>{item.source ?? ''}</span></button></li> })}</ol>
    {cursor && <button className="load-more" disabled={state === 'loading'} onClick={() => void load(cursor)} type="button">{state === 'loading' ? t('loading') : t('loadMore')}</button>}
    {selected && <aside className="detail-panel alert-detail" aria-label={t('alerts')}><header><button aria-label={t('back')} onClick={() => setSelected(undefined)} type="button">←</button><span>{t('alerts')}</span></header><div className="detail-scroll"><p className="detail-date">{when(selected.updatedAt, language)}</p><h2>{selected.state === 'USER_DISMISSED' || selected.state === 'CLEARED' ? t('alertCleared') : t('possibleScam')}</h2><p className="detail-lead">{selected.conversationPreview || t('contextLimited')}</p>{conversation && <section><span>{t('transcript')}</span><ol className="detail-transcript">{conversation.segments.map((segment) => <li key={segment.id}><p>{segment.text}</p></li>)}</ol></section>}</div></aside>}
  </section>
}
