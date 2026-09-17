import { deriveAndroidCompanion } from '../api/capability-view-model'
import type { ScutStatus } from '../api/contracts'
import { useI18n } from '../i18n'

interface DevicesPageProps { status: ScutStatus; onNotice(message: string): void }

export function DevicesPage({ status }: DevicesPageProps) {
  const { t } = useI18n()
  const companion = deriveAndroidCompanion(status)
  const connected = companion.status === 'Connected'
  const permissions = status.android.devices?.[0]?.permissions ?? {}
  const permissionRows: Array<[string, boolean]> = []
  if (typeof permissions.notifications === 'boolean') permissionRows.push([t('notifications'), permissions.notifications])
  if (typeof permissions.overlay === 'boolean') permissionRows.push([t('overlay'), permissions.overlay])
  if (typeof permissions.vibration === 'boolean') permissionRows.push([t('vibration'), permissions.vibration])
  return <section className="capability-page devices-page" aria-labelledby="devices-heading">
    <header className="page-toolbar"><span>{t('devices')}</span><small>{connected ? t('connected') : t('offline')}</small></header>
    <div className="page-heading"><span>{t('device')}</span><h1 id="devices-heading">{connected ? t('deviceHeading') : t('noHeartbeat')}</h1><p>{t('deviceBody')}</p></div>
    <div className="device-detail"><dl>
      <div><dt>{t('device')}</dt><dd>{companion.device ?? t('noHeartbeat')}</dd></div>
      <div><dt>{t('connection')}</dt><dd>{connected ? t('connected') : t('offline')}</dd></div>
      {permissionRows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ? t('granted') : t('needsPermission')}</dd></div>)}
    </dl></div>
  </section>
}
