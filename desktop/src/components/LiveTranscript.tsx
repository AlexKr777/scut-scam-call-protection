import { useState } from 'react'
import type { ScutMode } from '../api/contracts'
import type { LiveTranscriptState, TranscriptLine } from '../api/live-event-reducer'
import type { StreamConnection } from '../api/use-live-transcript'
import { RiskInspector } from './RiskInspector'
import { useI18n, type Translator } from '../i18n'

interface LiveTranscriptProps {
  connection: StreamConnection
  mode: ScutMode
  transcript: LiveTranscriptState
}

function speakerLabel(speaker: string, t: Translator): string {
  return speaker.toUpperCase() === 'CALLER' ? t('caller') : speaker.toUpperCase() === 'USER' ? t('you') : speaker
}

function transcriptTime(line: TranscriptLine, t: Translator): string {
  if (line.audioEndMs === undefined) return t('final')
  const totalSeconds = Math.max(0, Math.round(line.audioEndMs / 1000))
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, '0')}`
}

function connectionLabel(connection: StreamConnection, t: Translator): string {
  if (connection === 'live') return t('liveLocalStream')
  if (connection === 'reconnecting') return t('reconnecting')
  if (connection === 'unavailable') return t('streamUnavailable')
  return t('connecting')
}

export function LiveTranscript({ connection, mode, transcript }: LiveTranscriptProps) {
  const { t } = useI18n()
  const [selectedLineId, setSelectedLineId] = useState<string>()
  const selectedLine = transcript.lines.find((line) => line.id === selectedLineId)
  const inspectorOpen = Boolean(selectedLine?.decision)
  const hasCriticalSignal = transcript.lines.some((line) => line.decision?.level === 'CRITICAL')

  return (
    <section className={`live-transcript ${inspectorOpen ? 'has-inspector' : ''}`} aria-labelledby="live-transcript-heading">
      <header className="live-toolbar">
        <div className="live-call-meta">
          <span className={`live-stream-dot is-${connection}`} aria-hidden="true" />
          <span>{connectionLabel(connection, t)}</span>
          <i aria-hidden="true" />
          <span>{t('protectionLabel', { value: mode === 'OFF' ? t('modeOff') : mode === 'TEST' ? t('modeTest') : t('modeProtect') })}</span>
        </div>
        {hasCriticalSignal && <span className="critical-state">{t('criticalSignal')}</span>}
      </header>

      {transcript.latestAlert && <div className="alert-confirmation" role="status">
        <strong>{t('emitted')}</strong>
        <span>{t('emittedBody')}</span>
      </div>}

      <div className="transcript-layout">
        <article className="transcript-document">
          <header className="transcript-document-heading">
            <span>{t('conversation')}</span>
            <h1 id="live-transcript-heading">{t('liveTranscript')}</h1>
            <p>{t('conversationLiveBody')}</p>
          </header>

          <ol aria-live="polite" className="transcript-lines">
            {transcript.lines.map((line) => (
              <li className={`transcript-line ${line.decision ? `risk-${line.decision.level.toLowerCase()}` : ''}`} key={line.id}>
                <time>{transcriptTime(line, t)}</time>
                <div className="transcript-copy">
                  <span>{speakerLabel(line.speaker, t)}</span>
                  <p>{line.text}</p>
                  {line.decision && <button
                    aria-pressed={selectedLineId === line.id}
                    className="evidence-marker"
                    onClick={() => setSelectedLineId(line.id)}
                    type="button"
                  >
                    {t('evidence')}
                  </button>}
                </div>
              </li>
            ))}
          </ol>
        </article>

        {selectedLine?.decision && <RiskInspector line={selectedLine} onClose={() => setSelectedLineId(undefined)} />}
      </div>
    </section>
  )
}
