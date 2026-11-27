import { useState } from 'react'
import { Activity, BellRing, ChartNoAxesCombined, CircleAlert, CircleCheck, Clock3, Globe, Plus, ShieldAlert, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Incident, Monitor, Point, Summary, Window } from '../api/types'
import { CheckChart, WindowSwitch, windows } from '../components/chart'
import { Empty, ErrorPanel, IncidentStatus, SectionTitle, Skeleton, Status, formatDate, ms, percent } from '../components/ui'
import { Button } from '../components/ui/button'
import { useData } from '../hooks/data'
import { useSession } from '../hooks/session'
import { MonitorDialog } from './monitors'

export function Dashboard() {
  const [window, setWindow] = useState<Window>('24h')
  const [create, setCreate] = useState(false)
  const { user } = useSession()
  const period = '?window=' + window
  const summary = useData<Summary>('/dashboard/summary' + period)
  const latency = useData<Point[]>('/dashboard/response-times' + period)
  const availability = useData<Point[]>('/dashboard/availability' + period)
  const incidents = useData<Incident[]>('/dashboard/recent-incidents')
  const monitors = useData<Monitor[]>('/monitors?limit=5&sort=status')
  const certificates = useData<Pick<Monitor, 'id' | 'name' | 'ssl_valid' | 'ssl_expires_at'>[]>('/dashboard/ssl-warnings')
  const data = summary.data
  const periodName = windows.find(option => option.value === window)?.label
  const statItems = data && [
    { Icon: Globe, title: 'Мониторы', value: data.total, sub: 'Всего в рабочем пространстве', color: 'violet' },
    { Icon: CircleCheck, title: 'Работают', value: data.statuses.up ?? 0, sub: `Замедлены: ${data.statuses.degraded ?? 0}`, color: 'green' },
    { Icon: CircleAlert, title: 'Недоступны', value: data.statuses.down ?? 0, sub: 'Подтверждённые сбои', color: 'red' },
    { Icon: Activity, title: `Uptime · ${periodName}`, value: percent(data.uptime), sub: 'Доля успешных проверок', color: 'violet' },
    { Icon: Clock3, title: `Средний ответ · ${periodName}`, value: ms(data.average_ms), sub: 'По успешным проверкам', color: 'amber' },
  ]
  const chartPanels = [
    { Icon: ChartNoAxesCombined, title: 'Время ответа', description: 'Среднее по успешным проверкам', metric: 'latency', query: latency },
    { Icon: Activity, title: 'Доступность', description: 'Доля успешных проверок за каждый интервал', metric: 'availability', query: availability },
  ] as const
  return <>
    <SectionTitle title="Обзор" detail="Доступность и производительность ваших сервисов"
      actions={<div className="dashboard-actions"><WindowSwitch value={window} change={setWindow} />
        {!user?.is_demo && <Button onClick={() => setCreate(true)}><Plus size={18} /> Новый монитор</Button>}
      </div>} />
    {summary.isPending ? <Skeleton rows={2} /> : summary.isError ? <ErrorPanel error={summary.error} retry={() => void summary.refetch()} /> :
      <section className="metrics-grid dashboard-metrics" aria-label="Показатели">
        {statItems?.map(({ Icon, title, value, sub, color }) => <article className="metric" key={title}>
          <div><span className={`metric-icon metric-${color}`}><Icon size={17} /></span><span>{title}</span></div>
          <strong>{value}</strong><small>{sub}</small>
        </article>)}
      </section>}
    <div className="dashboard-panels">
      <div className="dashboard-stack">
        {chartPanels.map(({ Icon, title, description, metric, query }) => <section className="panel" key={metric}>
          <header className="panel-heading"><div><h2><Icon size={18} /> {title}</h2><p>{description}</p></div></header>
          {query.isPending ? <Skeleton /> : query.isError ? <ErrorPanel error={query.error} retry={() => void query.refetch()} /> :
            <CheckChart points={query.data} window={window} metric={metric} id={`dashboard-${metric}`} />}
        </section>)}
      </div>
      <div className="dashboard-stack">
        <section className="panel compact-panel">
          <header className="panel-heading"><div><h2><BellRing size={17} /> Инциденты</h2><p>Активных: {data?.open_incidents ?? '—'}</p></div>
            <Link to="/app/incidents">Все</Link></header>
          {incidents.isPending ? <Skeleton /> : incidents.isError ? <ErrorPanel error={incidents.error} retry={() => void incidents.refetch()} /> :
            !incidents.data.length ? <Empty icon={CircleCheck} title="Инцидентов нет" /> :
            <div className="compact-list">{incidents.data.map(item => <div key={item.id}>
              <div><Link to={`/app/monitors/${item.monitor_id}`}>{item.monitor_name}</Link><small>{formatDate(item.started_at)}</small></div>
              <IncidentStatus status={item.status} />
            </div>)}</div>}
        </section>
        <section className="panel compact-panel">
          <header className="panel-heading"><div><h2><ShieldAlert size={17} /> Предупреждения TLS</h2>
            <p>Ошибки сертификатов и истечение срока в ближайшие 30 дней</p></div></header>
          {certificates.isPending ? <Skeleton /> : certificates.isError ? <ErrorPanel error={certificates.error} retry={() => void certificates.refetch()} /> :
            !certificates.data.length ? <Empty icon={ShieldCheck} title="Предупреждений нет" /> :
            <div className="compact-list">{certificates.data.map(item => <div key={item.id}>
              <div><Link to={`/app/monitors/${item.id}`}>{item.name}</Link>
                <small>{item.ssl_valid === false ? 'Ошибка проверки сертификата' : `Действует до ${formatDate(item.ssl_expires_at)}`}</small></div>
              <span className={`status-label ${item.ssl_valid === false ? 'status-down' : 'status-degraded'}`}><i />
                {item.ssl_valid === false ? 'Ошибка TLS' : 'Истекает'}
              </span>
            </div>)}</div>}
        </section>
      </div>
    </div>
    <section className="panel">
      <header className="panel-heading"><div><h2><Globe size={18} /> Мониторы</h2><p>Текущее состояние сервисов</p></div>
        <Link to="/app/monitors">Все мониторы</Link></header>
      {monitors.isPending ? <Skeleton /> : monitors.isError ? <ErrorPanel error={monitors.error} retry={() => void monitors.refetch()} /> :
        !monitors.data.length ? <Empty title="Добавьте первый монитор" detail="Результат появится после первой фоновой проверки.">
          {!user?.is_demo && <Button size="small" onClick={() => setCreate(true)}><Plus size={16} /> Добавить монитор</Button>}
        </Empty> : <div className="compact-list dashboard-monitors">{monitors.data.map(item => <div key={item.id}>
          <div><Link to={`/app/monitors/${item.id}`}>{item.name}</Link><small>{item.url}</small></div>
          <Status status={item.status} /><span>{ms(item.last_response_time_ms)}</span><span>{percent(item.uptime)}</span>
        </div>)}</div>}
    </section>
    {create && <MonitorDialog close={() => setCreate(false)} />}
  </>
}
