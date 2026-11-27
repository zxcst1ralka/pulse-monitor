import { lazy, Suspense } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import { Brand, Skeleton } from './components/ui'
import { Button } from './components/ui/button'
import { Landing } from './pages/landing'

const Workspace = lazy(() => import('./layouts/workspace').then(module => ({ default: module.Workspace })))
const AuthPage = lazy(() => import('./pages/auth').then(module => ({ default: module.AuthPage })))
const Dashboard = lazy(() => import('./pages/dashboard').then(module => ({ default: module.Dashboard })))
const Incidents = lazy(() => import('./pages/incidents').then(module => ({ default: module.Incidents })))
const MonitorDetail = lazy(() => import('./pages/monitors').then(module => ({ default: module.MonitorDetail })))
const Monitors = lazy(() => import('./pages/monitors').then(module => ({ default: module.Monitors })))
const AdminPage = lazy(() => import('./pages/settings').then(module => ({ default: module.AdminPage })))
const Notifications = lazy(() => import('./pages/settings').then(module => ({ default: module.Notifications })))
const Profile = lazy(() => import('./pages/settings').then(module => ({ default: module.Profile })))
const PublicStatus = lazy(() => import('./pages/status-pages').then(module => ({ default: module.PublicStatus })))
const StatusPages = lazy(() => import('./pages/status-pages').then(module => ({ default: module.StatusPages })))

function NotFound() {
  return <div className="not-found"><Brand /><h1>Страница не найдена</h1>
    <p>Проверьте адрес или вернитесь на главную.</p><Button asChild><Link to="/">На главную</Link></Button></div>
}

export function App() {
  return <Suspense fallback={<div className="workspace-loading"><Skeleton /></div>}><Routes>
    <Route index element={<Landing />} />
    <Route path="login" element={<AuthPage key="login" registerAccount={false} />} />
    <Route path="register" element={<AuthPage key="register" registerAccount />} />
    <Route path="status/:slug" element={<PublicStatus />} />
    <Route path="app" element={<Workspace />}>
      <Route index element={<Dashboard />} />
      <Route path="monitors" element={<Monitors />} />
      <Route path="monitors/:id" element={<MonitorDetail />} />
      <Route path="incidents" element={<Incidents />} />
      <Route path="status-pages" element={<StatusPages />} />
      <Route path="notifications" element={<Notifications />} />
      <Route path="profile" element={<Profile />} />
      <Route path="admin" element={<AdminPage />} />
      <Route path="*" element={<NotFound />} />
    </Route>
    <Route path="*" element={<NotFound />} />
  </Routes></Suspense>
}
