import type { ReactNode } from 'react'
import { BrandMark } from './BrandMark'
import { useI18n } from '../i18n'

interface SidebarProps { activePage: PageName; onNavigate(page: PageName): void }
export type PageName = 'Home' | 'History' | 'Alerts' | 'Devices' | 'Settings'
type IconName = 'home' | 'history' | 'alerts' | 'devices' | 'settings'
const items: Array<{ label: PageName; icon: IconName }> = [
  { label: 'Home', icon: 'home' }, { label: 'History', icon: 'history' }, { label: 'Alerts', icon: 'alerts' }, { label: 'Devices', icon: 'devices' }, { label: 'Settings', icon: 'settings' },
]

function NavIcon({ name }: { name: IconName }): ReactNode {
  const paths: Record<IconName, ReactNode> = {
    home: <><path d="M4 9.5 10 4l6 5.5" /><path d="M6 8.2V16h8V8.2" /></>,
    history: <><path d="M5.3 5.2A7 7 0 1 1 3 10" /><path d="M3 5v5h5" /><path d="M10 6.5V10l2.5 1.5" /></>,
    alerts: <><path d="M5 13.5h10l-1.2-1.8V8a3.8 3.8 0 0 0-7.6 0v3.7Z" /><path d="M8.5 16h3" /></>,
    devices: <><rect height="12" rx="1.5" width="8" x="6" y="4" /><path d="M9 13.5h2" /></>,
    settings: <><circle cx="10" cy="10" r="2.5" /><path d="M10 3v2m0 10v2M3 10h2m10 0h2M5 5l1.4 1.4M13.6 13.6 15 15M15 5l-1.4 1.4M6.4 13.6 5 15" /></>,
  }
  return <svg aria-hidden="true" className="nav-icon" viewBox="0 0 20 20">{paths[name]}</svg>
}

export function Sidebar({ activePage, onNavigate }: SidebarProps) {
  const { t } = useI18n()
  const labels: Record<PageName, string> = { Home: t('home'), History: t('history'), Alerts: t('alerts'), Devices: t('devices'), Settings: t('settings') }
  return <aside className="sidebar">
    <div className="sidebar-brand" aria-label="SCUT"><BrandMark /><span>SCUT</span></div>
    <nav aria-label="Primary" className="primary-nav">{items.map((item) => <button aria-current={item.label === activePage ? 'page' : undefined} className="nav-item" key={item.label} onClick={() => onNavigate(item.label)} type="button"><NavIcon name={item.icon} /><span>{labels[item.label]}</span></button>)}</nav>
  </aside>
}
