import { useState } from 'react'
import { CircleCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Incident } from '../api/types'
import { Empty, ErrorPanel, IncidentStatus, Pagination, SectionTitle, Skeleton, duration, formatDate } from '../components/ui'
import { useData } from '../hooks/data'

export function IncidentTable({ rows }: { rows: Incident[] }) {
  if (!rows.length) return <Empty icon={CircleCheck} title="Инцидентов нет" />
  return <div className="table-scroll"><table>
    <thead><tr><th>Ресурс</th><th>Причина</th><th>Статус</th><th>Начало</th><th>Окончание</th><th>Длительность</th></tr></thead>
    <tbody>{rows.map(row => <tr key={row.id}>
      <td><Link className="table-link" to={`/app/monitors/${row.monitor_id}`}>{row.monitor_name}</Link></td>
      <td>{row.reason}</td><td><IncidentStatus status={row.status} /></td><td>{formatDate(row.started_at)}</td>
      <td>{formatDate(row.resolved_at)}</td><td>{duration(row.duration_seconds)}</td>
    </tr>)}</tbody>
  </table></div>
}

export function Incidents() {
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const size = 20
  const query = useData<Incident[]>(`/incidents?limit=${size}&offset=${offset}` + (status ? '&status=' + status : ''))
  return <>
    <SectionTitle title="Инциденты" detail="Подтверждённые сбои и история восстановления" />
    <section className="panel">
      <div className="table-toolbar"><select aria-label="Статус инцидента" value={status} onChange={event => {
        setStatus(event.target.value); setOffset(0)
      }}><option value="">Все инциденты</option><option value="ongoing">Активные</option><option value="resolved">Закрытые</option></select></div>
      {query.isPending ? <Skeleton /> : query.isError ? <ErrorPanel error={query.error} retry={() => void query.refetch()} /> :
        <><IncidentTable rows={query.data} /><Pagination offset={offset} size={size} count={query.data.length} change={setOffset} /></>}
    </section>
  </>
}
