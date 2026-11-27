import { useState } from 'react'
import { Activity, AlertCircle, Check, ChevronLeft, ChevronRight, CircleAlert, Globe, Moon, Sun } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { MonitorStatus } from '../api/types'
import { Button } from './ui/button'
import { Dialog } from './ui/dialog'

export function Brand({ to = '/' }: { to?: string }) {
  return <Link className="brand" to={to}><img src="/pulse.svg" alt="" width="34" height="34" />Pulse<span>Monitor</span></Link>
}

export const labels: Record<MonitorStatus, string> = {
  up: 'Работает', down: 'Недоступен', degraded: 'Замедлен', pending: 'Ожидает проверки', paused: 'На паузе',
}

export function Status({ status }: { status: MonitorStatus }) {
  return <span className={`status-label status-${status}`}><i />{labels[status]}</span>
}

export function IncidentStatus({ status }: { status: 'ongoing' | 'resolved' }) {
  return <span className={`status-label status-${status === 'ongoing' ? 'down' : 'up'}`}><i />
    {status === 'ongoing' ? 'Активен' : 'Закрыт'}
  </span>
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return <div className="skeleton-panel" role="status"><span className="sr-only">Загрузка</span>
    {Array.from({ length: rows }, (_, index) => <div className="skeleton" key={index} />)}
  </div>
}

export function ErrorPanel({ error, retry }: { error: unknown; retry?: () => void }) {
  return <div className="state-panel" role="alert"><AlertCircle size={25} /><strong>Не удалось загрузить данные</strong>
    <p>{error instanceof Error ? error.message : 'Попробуйте ещё раз'}</p>
    {retry && <Button variant="secondary" size="small" onClick={retry}>Повторить</Button>}
  </div>
}

export function Empty({ title, detail, icon: Icon = Globe, children }: {
  title: string; detail?: string; icon?: typeof Globe; children?: React.ReactNode
}) {
  return <div className="state-panel"><span className="empty-icon"><Icon size={22} /></span>
    <strong>{title}</strong>{detail && <p>{detail}</p>}{children}
  </div>
}

export function Pagination({ offset, size, count, change }: { offset: number; size: number; count: number; change: (value: number) => void }) {
  if (offset === 0 && count < size) return null
  return <div className="pagination">
    <span>Страница {Math.floor(offset / size) + 1}</span>
    <Button size="icon" variant="secondary" disabled={!offset} aria-label="Предыдущая страница"
      onClick={() => change(Math.max(0, offset - size))}><ChevronLeft size={16} /></Button>
    <Button size="icon" variant="secondary" disabled={count < size} aria-label="Следующая страница"
      onClick={() => change(offset + size)}><ChevronRight size={16} /></Button>
  </div>
}

export function Confirm({ title, detail, close, confirm, pending }: {
  title: string; detail: string; close: () => void; confirm: () => void; pending: boolean
}) {
  return <Dialog open onClose={close} title={title} description={detail}>
    <div className="form-actions"><Button variant="secondary" onClick={close}>Отмена</Button>
      <Button variant="danger" onClick={confirm} disabled={pending}>{pending ? 'Выполняется…' : 'Подтвердить'}</Button></div>
  </Dialog>
}

export function ThemeSwitch() {
  const [light, setLight] = useState(document.documentElement.dataset.theme === 'light')
  const Icon = light ? Moon : Sun
  const label = light ? 'Тёмная тема' : 'Светлая тема'
  return <Button variant="ghost" size="icon" title={label} aria-label={label} onClick={() => {
    const theme = light ? 'dark' : 'light'
    document.documentElement.dataset.theme = theme
    localStorage.setItem('pulse-theme', theme)
    setLight(!light)
  }}><Icon size={17} /></Button>
}

export function ToastIcon({ error }: { error: boolean }) {
  return error ? <CircleAlert size={18} /> : <Check size={18} />
}

export const formatDate = (value: string | null | undefined) => value ? new Intl.DateTimeFormat('ru', {
  dateStyle: 'short', timeStyle: 'short',
}).format(new Date(value)) : '—'
export const number = (value: number, digits = 0) => value.toLocaleString('ru', { maximumFractionDigits: digits })
export const percent = (value: number | null | undefined) => value == null ? 'Нет данных' : number(value, 2) + '%'
export const ms = (value: number | null | undefined) => value == null ? '—' : number(value) + ' мс'
export function duration(value: number | null) {
  if (value == null) return '—'
  if (value < 60) return value + ' с'
  if (value < 3600) return Math.floor(value / 60) + ' мин'
  return Math.floor(value / 3600) + ' ч ' + Math.floor(value % 3600 / 60) + ' мин'
}

export function SectionTitle({ title, detail, actions }: { title: string; detail?: string; actions?: React.ReactNode }) {
  return <header className="section-heading"><div><h1>{title}</h1>{detail && <p>{detail}</p>}</div>{actions}</header>
}

export function SyntheticNotice() {
  return <aside className="synthetic"><Activity size={16} /> Демонстрационные данные. Результаты проверок синтетические.</aside>
}
