import { useState } from 'react'
import { Activity, BellRing, ChartNoAxesCombined, CircleCheck, Clock3, Globe, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Incident, Monitor, Point, Summary, Window } from '../api/types'
import { LatencyChart, WindowSwitch } from '../components/chart'
import { Empty, ErrorPanel, IncidentStatus, SectionTitle, Skeleton, Status, formatDate, ms, percent } from '../components/ui'
import { Button } from '../components/ui/button'
import { useData } from '../hooks/data'
import { useSession } from '../hooks/session'
import { MonitorDialog } from './monitors'

export function Dashboard() {
  const [window, setWindow] = useState<Window>('24h')
  const [create, setCreate] = useState(false)
  const { user } = useSession()
  const summary = useData<Summary>('/dashboard/summary')
  const series = useData<Point[]>('/dashboard/response-times?window=' + window)
  const incidents = useData<Incident[]>('/dashboard/recent-incidents')
  const monitors = useData<Monitor[]>('/monitors?limit=5&sort=status')
  const data = summary.data
  const statItems = data && [
    { Icon: Globe, title: 'Мониторы', value: data.total, sub: 'Всего в рабочем пространстве', color: 'violet' },
    { Icon: CircleCheck, title: 'Работают', value: data.statuses.up ?? 0, sub: `${data.statuses.down ?? 0} недоступны · ${data.statuses.degraded ?? 0} замедлены`, color: 'green' },
    { Icon: Activity, title: 'Uptime · 24 ч', value: percent(data.uptime), sub: 'Доля успешных проверок', color: 'violet' },
    { Icon: Clock3, title: 'Средний ответ · 24 ч', value: ms(data.average_ms), sub: 'По успешным проверкам', color: 'amber' },
  ]
  return <>
    <SectionTitle title="Обзор" detail="Доступность и производительность ваших сервисов"
      actions={!user?.is_demo && <Button onClick={() => setCreate(true)}><Plus size={18} /> Новый монитор</Button>} />
    {summary.isPending ? <Skeleton rows={2} /> : summary.isError ? <ErrorPanel error={summary.error} retry={() => void summary.refetch()} /> :
      <section className="metrics-grid" aria-label="Показатели">
        {statItems?.map(({ Icon, title, value, sub, color }) => <article className="metric" key={title}>
          <div><span className={`metric-icon metric-${color}`}><Icon size={17} /></span><span>{title}</span></div>
          <strong>{value}</strong><small>{sub}</small>
        </article>)}
      </section>}
    <div className="dashboard-panels">
      <section className="panel">
        <header className="panel-heading"><div><h2><ChartNoAxesCombined size={18} /> Время ответа</h2><p>Среднее по успешным проверкам</p></div>
          <WindowSwitch value={window} change={setWindow} /></header>
        {series.isPending ? <Skeleton /> : series.isError ? <ErrorPanel error={series.error} retry={() => void series.refetch()} /> :
          <LatencyChart points={series.data} window={window} id="dashboard-latency" />}
      </section>
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
