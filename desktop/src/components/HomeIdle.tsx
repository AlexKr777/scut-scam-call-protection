import type { HomeState } from '../api/contracts'
import { ProtectionGlyph } from './ProtectionGlyph'
import { useI18n } from '../i18n'

interface HomeIdleProps {
  state: HomeState
}

interface SetupItemProps {
  label: string
  value: string
  detail: string
  tone: HomeState['modeTone']
}

function SetupItem({ label, value, detail, tone }: SetupItemProps) {
  return (
    <li className="setup-item">
      <span className={`setup-indicator tone-${tone}`} aria-hidden="true" />
      <div>
        <span className="setup-label">{label}</span>
        <strong>{value}</strong>
        <p>{detail}</p>
      </div>
    </li>
  )
}

export function HomeIdle({ state }: HomeIdleProps) {
  const { t } = useI18n()
  return (
    <section className="home" aria-labelledby="home-heading">
      <header className="home-toolbar">
        <span className="home-location">{t('home')}</span>
        <span className="home-source"><i />{t('homeLive')}</span>
      </header>

      <div className="home-stage">
        <div className="home-primary">
          <div className="mode-line">
            <span className={`mode-dot tone-${state.modeTone}`} aria-hidden="true" />
            <span>{t('protectionLabel', { value: state.modeLabel })}</span>
          </div>

          <div className="state-lockup">
            <ProtectionGlyph tone={state.modeTone} />
            <div className="home-intro">
              <h1 id="home-heading">{state.headline}</h1>
              <p className="home-detail">{state.detail}</p>
            </div>
          </div>

          <div className="truth-note">
            <span>{t('currentBehavior')}</span>
            <p>{t('currentBehaviorBody')}</p>
          </div>
        </div>

        <aside className="setup-rail" aria-labelledby="setup-heading">
          <header>
            <span>{t('systemOverview')}</span>
            <h2 id="setup-heading">{t('currentSetup')}</h2>
            <p>{t('localSource')}</p>
          </header>
          <ul>
            <SetupItem detail={state.captureMessage} label={t('audioPath')} tone={state.captureTone} value={state.captureLabel} />
            <SetupItem detail={state.androidDetail} label={t('companion')} tone={state.androidTone} value={state.androidLabel} />
            <SetupItem
              detail={state.lastActivityAt ?? t('noRecentBody')}
              label={t('recentActivity')}
              tone="neutral"
              value={state.lastActivity}
            />
          </ul>
        </aside>
      </div>

      <footer className="home-footnote">
        <span>{t('privateDefault')}</span>
        <i aria-hidden="true" />
        <span>{t('localPrivacy')}</span>
      </footer>
    </section>
  )
}
