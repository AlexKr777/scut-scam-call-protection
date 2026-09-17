import type { HomeTone } from '../api/contracts'
import { useI18n } from '../i18n'

export function ProtectionGlyph({ tone }: { tone: HomeTone }) {
  const { t } = useI18n()
  return (
    <div className={`protection-glyph is-${tone}`} aria-label={t('protectionState')} role="img">
      <svg aria-hidden="true" viewBox="0 0 180 180">
        <path className="glyph-outer" d="M76 22H54c-17.7 0-32 14.3-32 32v72c0 17.7 14.3 32 32 32h22" />
        <path className="glyph-inner" d="M76 50H59c-5 0-9 4-9 9v62c0 5 4 9 9 9h17" />
        <path className="glyph-signal" d="M96 110V70m20 54V56m20 51V73" />
        <circle className="glyph-anchor" cx="96" cy="127" r="4" />
      </svg>
      <span>{tone === 'safe' ? t('ready') : tone === 'attention' ? t('check') : t('quiet')}</span>
    </div>
  )
}
