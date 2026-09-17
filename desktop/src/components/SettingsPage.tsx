import { useState } from 'react'
import type { DiagnosticName, PairingPayload, ScutMode, ScutStatus } from '../api/contracts'
import { useI18n, type AppLanguage } from '../i18n'

interface SettingsPageProps { status: ScutStatus; onStatus(status: ScutStatus): void; onNotice(message: string): void }
const diagnostics: DiagnosticName[] = ['capture', 'guarded-transcription', 'network', 'earbuds', 'predemo']

export function SettingsPage({ onNotice, onStatus, status }: SettingsPageProps) {
  const { language, setLanguage, t } = useI18n()
  const [busy, setBusy] = useState<string>()
  const [input, setInput] = useState('')
  const [recordingUrl, setRecordingUrl] = useState<string>()
  const [pairing, setPairing] = useState<PairingPayload>()

  function isStatus(value: unknown): value is ScutStatus { return typeof value === 'object' && value !== null && 'mode' in value && 'audio' in value }
  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(label)
    try { const result = await action(); if (isStatus(result)) onStatus(result); onNotice(`${label} · ${t('available')}`) }
    catch { onNotice(t('unavailable')) }
    finally { setBusy(undefined) }
  }

  return <section className="capability-page settings-page" aria-labelledby="settings-heading">
    <header className="page-toolbar"><span>{t('settings')}</span><small>{t('privateDefault')}</small></header>
    <div className="page-heading"><span>{t('settingsEyebrow')}</span><h1 id="settings-heading">{t('settingsTitle')}</h1><p>{t('settingsBody')}</p></div>
    <section className="settings-section"><header><span>{t('language')}</span><h2>{t('languageBody')}</h2></header><div className="mode-controls language-controls" role="group" aria-label={t('language')}>
      {([['en', t('english')], ['ru', t('russian')], ['ro', t('romanian')]] as Array<[AppLanguage, string]>).map(([value, label]) => <button aria-pressed={language === value} key={value} onClick={() => setLanguage(value)} type="button">{label}</button>)}
    </div></section>
    <section className="settings-section"><header><span>{t('protectionMode')}</span><h2>{t('current', { value: status.mode === 'OFF' ? t('modeOff') : status.mode === 'TEST' ? t('modeTest') : t('modeProtect') })}</h2></header><div className="mode-controls" role="group" aria-label={t('protectionMode')}>
      {(['OFF', 'TEST', 'PROTECT'] as ScutMode[]).map((mode) => <button aria-pressed={status.mode === mode} disabled={Boolean(busy)} key={mode} onClick={() => void run(mode, () => window.scut.setMode(mode))} type="button">{mode === 'OFF' ? t('modeOff') : mode === 'TEST' ? t('modeTest') : t('modeProtect')}</button>)}
    </div></section>
    <details className="advanced-disclosure"><summary><span>{t('advanced')}</span><small>{t('advancedBody')}</small></summary><div className="advanced-content">
      <section className="settings-section technical-facts"><header><span>{t('serviceState')}</span><h2>{status.controlPlane?.state ?? 'UNAVAILABLE'}</h2></header><dl><div><dt>{t('serviceReason')}</dt><dd>{status.controlPlane?.reason ?? '—'}</dd></div><div><dt>{t('decisionEpoch')}</dt><dd>{status.controlPlane?.decisionEpoch ?? 0}</dd></div><div><dt>{t('liveSession')}</dt><dd>{status.controlPlane?.liveSession ? 'ACTIVE' : 'NONE'}</dd></div></dl></section>
      <section className="settings-section"><header><span>{t('explicitTests')}</span><h2>{t('diagnostics')}</h2></header><ul className="diagnostic-list">{diagnostics.map((name) => <li key={name}><strong>{name.replaceAll('-', ' ')}</strong><button disabled={Boolean(busy)} onClick={() => void run(name, () => window.scut.runDiagnostic(name))} type="button">{t('run')}</button></li>)}</ul></section>
      <section className="settings-section diagnostic-input"><header><span>{t('diagnostics')}</span><h2>{t('analyzeText')}</h2></header><form onSubmit={(event) => { event.preventDefault(); void run(t('analyzeText'), async () => { const result = await window.scut.submitDiagnosticTranscript(input); setInput(''); return result }) }}><label htmlFor="diagnostic-transcript">{t('stableTranscript')}</label><textarea id="diagnostic-transcript" maxLength={4000} onChange={(event) => setInput(event.target.value)} value={input} /><button disabled={Boolean(busy) || !input.trim()} type="submit">{t('analyze')}</button></form></section>
      <section className="settings-section recording-panel"><header><span>{t('diagnostics')}</span><h2>{t('recording')}</h2></header><button onClick={() => void run(t('recording'), async () => { const url = await window.scut.getRecordingUrl(); setRecordingUrl(url) })} type="button">{t('loadRecording')}</button>{recordingUrl && <audio controls src={recordingUrl} />}</section>
      <section className="settings-section"><header><span>{t('devices')}</span><h2>{t('pairHeading')}</h2></header><p>{t('pairBody')}</p><button className="quiet-action" onClick={() => void run(t('createPairing'), async () => { const value = await window.scut.createPairing(); setPairing(value); return value })} type="button">{t('createPairing')}</button>{pairing && <div className="pairing-result"><pre>{JSON.stringify(pairing, null, 2)}</pre><button onClick={() => void navigator.clipboard.writeText(JSON.stringify(pairing)).then(() => onNotice(t('copied')))} type="button">{t('copy')}</button></div>}</section>
    </div></details>
  </section>
}
