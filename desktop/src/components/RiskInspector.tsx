import type { TranscriptLine } from '../api/live-event-reducer'
import { useI18n } from '../i18n'

interface RiskInspectorProps { line: TranscriptLine; onClose(): void }
function human(value: string): string { return value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()) }

export function RiskInspector({ line, onClose }: RiskInspectorProps) {
  const { t } = useI18n()
  const decision = line.decision
  if (!decision) return null
  return <aside aria-labelledby="inspector-heading" className="risk-inspector">
    <header className="inspector-header"><div><span>{t('evidenceLabel')}</span><h2 id="inspector-heading">{t('evidence')}</h2></div><button aria-label={t('close')} className="inspector-close" onClick={onClose} type="button">×</button></header>
    <p className="inspector-summary">{decision.warning ?? human(decision.reason)}</p>
    <dl className="inspector-facts"><div><dt>{t('decision')}</dt><dd>{human(decision.reason)}</dd></div><div><dt>{t('signal')}</dt><dd>{human(decision.level)}</dd></div></dl>
    {decision.evidence.length > 0 && <section className="inspector-section"><h3>{t('evidence')}</h3><ul className="evidence-list">{decision.evidence.map((item, index) => <li key={`${item.code}-${index}`}>{item.originalSpan ? <span>“{item.originalSpan}”</span> : <strong>{human(item.code)}</strong>}</li>)}</ul></section>}
  </aside>
}
