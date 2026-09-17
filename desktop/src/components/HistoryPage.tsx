import { useEffect, useState } from 'react'
import type { ConversationDetail, ConversationSummary } from '../api/contracts'
import { useI18n } from '../i18n'

function when(value: string, language: string): string {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? '' : new Intl.DateTimeFormat(language, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function ConversationPanel({ id, onClose, onDeleted }: { id: string; onClose(): void; onDeleted(id: string): void }) {
  const { language, t } = useI18n()
  const [conversation, setConversation] = useState<ConversationDetail>()
  const [error, setError] = useState(false)
  useEffect(() => {
    let active = true
    window.scut.getConversation(id).then((value) => { if (active) setConversation(value.conversation) }).catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [id])

  async function remove() {
    if (!window.confirm(t('deleteConfirm'))) return
    try { await window.scut.deleteConversation(id); onDeleted(id); onClose() } catch { setError(true) }
  }

  return <aside className="detail-panel" aria-label={t('conversation')}>
    <header><button aria-label={t('back')} onClick={onClose} type="button">←</button><span>{t('conversation')}</span><button className="danger-link" onClick={() => void remove()} type="button">{t('delete')}</button></header>
    {error && <div className="detail-state">{t('unavailable')}</div>}
    {!conversation && !error && <div className="detail-state">{t('loading')}</div>}
    {conversation && <div className="detail-scroll">
      <p className="detail-date">{when(conversation.startedAt, language)}</p>
      <h2>{conversation.protectedReceiverName || t('unknownPhone')}</h2>
      <section><span>{t('transcript')}</span>
        {conversation.segments.length === 0 && <p className="muted-copy">{t('noTranscript')}</p>}
        <ol className="detail-transcript">{conversation.segments.map((segment) => <li key={segment.id}><time>{when(segment.ended_at ?? '', language)}</time><p>{segment.text}</p></li>)}</ol>
      </section>
      {conversation.incidents.map((incident) => {
        const cleared = incident.state === 'CLEARED' || incident.state === 'USER_DISMISSED'
        const excerpts = (incident.incident_evidence ?? []).flatMap((item) => item.payload?.text ? [item.payload.text] : [])
        return <section className={`detail-incident ${cleared ? 'is-cleared' : ''}`} key={incident.id}><span>{t('evidence')}</span><h3>{cleared ? t('alertCleared') : t('possibleScam')}</h3>{excerpts.length ? excerpts.map((text, index) => <blockquote key={index}>{text}</blockquote>) : <p className="muted-copy">{t('contextLimited')}</p>}</section>
      })}
    </div>}
  </aside>
}

export function HistoryPage({ onNotice }: { onNotice(message: string): void }) {
  const { language, t } = useI18n()
  const [items, setItems] = useState<ConversationSummary[]>([])
  const [cursor, setCursor] = useState<string>()
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [offline, setOffline] = useState(false)
  const [selected, setSelected] = useState<string>()

  async function load(next?: string) {
    setState('loading')
    try {
      const page = await window.scut.getHistory(next)
      setItems((current) => next ? [...current, ...page.conversations] : page.conversations)
      setCursor(page.nextCursor ?? undefined); setOffline(Boolean(page.offline)); setState('ready')
    } catch { setState('error') }
  }
  useEffect(() => { void load() }, [])

  return <section className="capability-page archive-page" aria-labelledby="history-heading">
    <header className="page-toolbar"><span>{t('history')}</span><small>{items.length}</small></header>
    <div className="page-heading"><span>{t('historyEyebrow')}</span><h1 id="history-heading">{t('historyTitle')}</h1><p>{t('historyBody')}</p></div>
    {offline && <p className="archive-banner">{t('offlineCached')}</p>}
    {state === 'loading' && items.length === 0 && <div className="archive-state">{t('loading')}</div>}
    {state === 'error' && <div className="archive-state"><p>{t('unavailable')}</p><button onClick={() => void load()} type="button">{t('retry')}</button></div>}
    {state === 'ready' && items.length === 0 && <div className="archive-empty"><h2>{t('historyEmpty')}</h2><p>{t('historyEmptyBody')}</p></div>}
    <ol className="archive-list">{items.map((item, index) => <li key={item.id} style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}><button onClick={() => setSelected(item.id)} type="button"><div><time>{when(item.startedAt, language)}</time><strong>{item.protectedReceiverName || t('unknownPhone')}</strong><p>{item.preview || t('noTranscript')}</p></div><span className={item.incidentState ? 'attention-mark' : ''}>{item.incidentState ? (item.incidentState === 'USER_DISMISSED' ? t('alertCleared') : t('possibleScam')) : t('duration', { value: item.durationSeconds ?? 0 })}</span></button></li>)}</ol>
    {cursor && <button className="load-more" disabled={state === 'loading'} onClick={() => void load(cursor)} type="button">{state === 'loading' ? t('loading') : t('loadMore')}</button>}
    {selected && <ConversationPanel id={selected} onClose={() => setSelected(undefined)} onDeleted={(id) => { setItems((current) => current.filter((item) => item.id !== id)); onNotice(t('deleted')) }} />}
  </section>
}
