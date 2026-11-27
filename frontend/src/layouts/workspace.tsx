import { Suspense, useEffect, useRef, useState } from 'react'
import { Activity, Bell, Globe, LayoutDashboard, LogOut, Menu, Radio, Shield, Siren, X } from 'lucide-react'
import { Navigate, NavLink, Outlet, useLocation } from 'react-router-dom'
import { signOut } from '../api/client'
import { Brand, Skeleton, SyntheticNotice, ThemeSwitch } from '../components/ui'
import { Button } from '../components/ui/button'
import { useSession } from '../hooks/session'
import { useToast } from '../hooks/toast'

const mainNavigation = [
  { to: '/app', label: 'Обзор', Icon: LayoutDashboard },
  { to: '/app/monitors', label: 'Мониторы', Icon: Globe },
  { to: '/app/incidents', label: 'Инциденты', Icon: Siren },
  { to: '/app/status-pages', label: 'Статус-страницы', Icon: Radio },
]
const settingsNavigation = [
  { to: '/app/notifications', label: 'Уведомления', Icon: Bell },
  { to: '/app/admin', label: 'Администрирование', Icon: Shield },
]
const profile = { to: '/app/profile', label: 'Профиль' }

export function Workspace() {
  const [menu, setMenu] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const { user, loading } = useSession()
  const toast = useToast()
  const location = useLocation()
  const menuToggle = useRef<HTMLButtonElement>(null)
  const menuClose = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (menu) menuClose.current?.focus()
  }, [menu])
  if (loading) return <main className="workspace-loading"><Brand /><Skeleton /></main>
  if (!user) return <Navigate to="/login" replace />
  const items = user.role === 'admin' ? settingsNavigation : settingsNavigation.slice(0, 1)
  const current = [...mainNavigation, ...items, profile].find(item => item.to !== '/app' && location.pathname.startsWith(item.to))
  function closeMenu() {
    setMenu(false)
    menuToggle.current?.focus()
  }
  function navigation(links: typeof mainNavigation) {
    return links.map(({ to, label, Icon }) => <NavLink end={to === '/app'} key={to} to={to} onClick={() => setMenu(false)}>
      <Icon size={17} />{label}
    </NavLink>)
  }
  return <div className="workspace">
    <aside id="workspace-menu" className={`sidebar ${menu ? 'sidebar-open' : ''}`} onKeyDown={event => {
      if (menu && event.key === 'Escape') closeMenu()
    }}>
      <div className="sidebar-brand"><Brand to="/app" />
        <Button ref={menuClose} className="sidebar-close" variant="ghost" size="icon" aria-label="Закрыть меню" onClick={closeMenu}><X size={19} /></Button></div>
      <nav aria-label="Рабочее пространство"><div className="sidebar-caption">Мониторинг</div>{navigation(mainNavigation)}
        <div className="sidebar-caption settings-caption">Настройки</div>{navigation(items)}</nav>
      <div className="sidebar-user">
        <NavLink className="sidebar-profile" to={profile.to} aria-label={profile.label} title={profile.label} onClick={() => setMenu(false)}>
          <span className="avatar">{user.name.slice(0, 1).toUpperCase()}</span>
          <div><strong>{user.name}</strong><small>{user.email}</small></div>
        </NavLink>
        <ThemeSwitch />
        <Button aria-label="Выйти" title="Выйти" variant="ghost" size="icon" disabled={leaving} onClick={async () => {
          setLeaving(true)
          try { await signOut() }
          catch (error) { toast(error instanceof Error ? error.message : 'Не удалось выйти', true) }
          finally { setLeaving(false) }
        }}><LogOut size={17} /></Button>
      </div>
    </aside>
    {menu && <button className="mobile-overlay" aria-label="Закрыть меню" onClick={closeMenu} />}
    <div className="workspace-body">
      <header className="workspace-bar">
        <div>
          <Button ref={menuToggle} className="menu-toggle" size="icon" variant="ghost" aria-label="Открыть меню" aria-expanded={menu}
            aria-controls="workspace-menu" onClick={() => setMenu(true)}><Menu size={20} /></Button>
          <Activity size={16} /><span>Рабочее пространство</span><i>/</i><strong>{current?.label ?? 'Обзор'}</strong>
        </div>
      </header>
      <main className="work-content">
        {user.is_demo && <SyntheticNotice />}
        <Suspense fallback={<Skeleton />}><Outlet /></Suspense>
      </main>
    </div>
  </div>
}
