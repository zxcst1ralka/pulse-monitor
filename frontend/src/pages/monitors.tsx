import { useState } from 'react'
import { Activity, ChevronLeft, Clock3, Globe, Pause, Pencil, Play, Plus, Search, ShieldCheck, Trash2, Zap } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api } from '../api/client'
import type { Check, Incident, Monitor, MonitorInput, MonitorStatus, Stats, Window } from '../api/types'
import { LatencyChart, WindowSwitch, windows } from '../components/chart'
import { Confirm, Empty, ErrorPanel, Pagination, SectionTitle, Skeleton, Status, duration, formatDate, labels, ms, percent } from '../components/ui'
import { Button } from '../components/ui/button'
import { Dialog } from '../components/ui/dialog'
import { useAction, useData } from '../hooks/data'
import { useSession } from '../hooks/session'
import { IncidentTable } from './incidents'

const intervals = [60, 300, 600, 900, 1800, 3600]
const refresh = ['/monitors', '/dashboard', '/incidents']
const monitorForm = z.object({
  name: z.string().trim().min(1, 'Введите название').max(100),
  url: z.url({ protocol: /^https?$/, error: 'Введите полный HTTP(S)-адрес' }).max(2048),
  type: z.enum(['http', 'keyword']),
  interval_seconds: z.number().refine(value => intervals.includes(value), 'Выберите интервал'),
  timeout_seconds: z.number().int().min(5).max(30),
  expected_status_code: z.number().int().min(100).max(599),
  keyword: z.string().max(200).nullable(),
  response_threshold_ms: z.number().int().min(100).max(30_000),
  notifications_enabled: z.boolean(),
}).superRefine((value, ctx) => {
  if (value.type === 'keyword' && !value.keyword?.trim()) {
    ctx.addIssue({ code: 'custom', path: ['keyword'], message: 'Введите ключевое слово' })
  }
})
const defaults: MonitorInput = {
  name: '', url: '', type: 'http', interval_seconds: 300, timeout_seconds: 10,
  expected_status_code: 200, keyword: null, response_threshold_ms: 2000, notifications_enabled: true,
}

function inputOf(monitor?: Monitor): MonitorInput {
  if (!monitor) return defaults
  return {
    name: monitor.name, url: monitor.url, type: monitor.type, interval_seconds: monitor.interval_seconds,
    timeout_seconds: monitor.timeout_seconds, expected_status_code: monitor.expected_status_code, keyword: monitor.keyword,
    response_threshold_ms: monitor.response_threshold_ms, notifications_enabled: monitor.notifications_enabled,
  }
}

export function MonitorDialog({ monitor, close }: { monitor?: Monitor; close: () => void }) {
  const save = useAction(
    (body: MonitorInput) => api<Monitor>(monitor ? `/monitors/${monitor.id}` : '/monitors', {
      method: monitor ? 'PATCH' : 'POST', body: { ...body, keyword: body.type === 'keyword' ? body.keyword : null },
    }), monitor ? 'Монитор обновлён' : 'Монитор добавлен', refresh,
  )
  const { register, handleSubmit, watch, formState: { errors } } = useForm({
    defaultValues: inputOf(monitor), resolver: zodResolver(monitorForm),
  })
  return <Dialog open onClose={close} title={monitor ? 'Настройки монитора' : 'Новый монитор'}
    description="Планировщик проверяет публичные HTTP(S)-адреса через заданный интервал.">
    <form className="dialog-form" noValidate onSubmit={handleSubmit(body => save.mutate(body, { onSuccess: close }))}>
      <label>Название<input placeholder="Например, Production API" {...register('name')} />
        {errors.name && <small className="field-error">{errors.name.message}</small>}</label>
      <label>Публичный URL<input type="url" placeholder="https://example.com" {...register('url')} />
        {errors.url && <small className="field-error">{errors.url.message}</small>}</label>
      <div className="form-grid">
        <label>Тип проверки<select {...register('type')}><option value="http">HTTP / HTTPS</option><option value="keyword">Ключевое слово</option></select></label>
        <label>Интервал<select {...register('interval_seconds', { valueAsNumber: true })}>
          {intervals.map(value => <option key={value} value={value}>{duration(value)}</option>)}</select></label>
      </div>
      {watch('type') === 'keyword' && <label>Ключевое слово<input {...register('keyword')} />
        {errors.keyword && <small className="field-error">{errors.keyword.message}</small>}</label>}
      <div className="form-grid form-grid-three">
        <label>Таймаут, с<input type="number" min={5} max={30} {...register('timeout_seconds', { valueAsNumber: true })} />
          {errors.timeout_seconds && <small className="field-error">От 5 до 30 секунд</small>}</label>
        <label>HTTP-код<input type="number" min={100} max={599} {...register('expected_status_code', { valueAsNumber: true })} />
          {errors.expected_status_code && <small className="field-error">От 100 до 599</small>}</label>
        <label>Порог, мс<input type="number" min={100} max={30_000} {...register('response_threshold_ms', { valueAsNumber: true })} />
          {errors.response_threshold_ms && <small className="field-error">От 100 до 30 000 мс</small>}</label>
      </div>
      <label className="checkbox"><input type="checkbox" {...register('notifications_enabled')} /> Отправлять уведомления</label>
      {save.isError && <p className="field-error" role="alert">{save.error.message}</p>}
      <div className="form-actions"><Button variant="secondary" onClick={close}>Отмена</Button>
        <Button type="submit" disabled={save.isPending}>{save.isPending ? 'Сохранение…' : 'Сохранить'}</Button></div>
    </form>
  </Dialog>
}

function useMonitorAction() {
  return useAction(({ id, action }: { id: string; action: string }) => api(
    '/monitors/' + id + (action === 'delete' ? '' : '/' + action), { method: action === 'delete' ? 'DELETE' : 'POST' },
  ), 'Действие выполнено', refresh)
}

function MonitorActions({ monitor, busy, run, edit, remove }: {
  monitor: Monitor; busy: boolean; run: (action: string) => void; edit: () => void; remove: () => void
}) {
  const StateIcon = monitor.is_active ? Pause : Play
  const label = monitor.is_active ? 'Пауза' : 'Возобновить'
  return <div className="inline-actions">
    <Button variant="ghost" size="icon" aria-label="Проверить сейчас" title="Проверить сейчас" disabled={busy || !monitor.is_active}
      onClick={() => run('check')}><Zap size={16} /></Button>
    <Button variant="ghost" size="icon" aria-label={label} title={label} disabled={busy}
      onClick={() => run(monitor.is_active ? 'pause' : 'resume')}><StateIcon size={16} /></Button>
    <Button variant="ghost" size="icon" aria-label="Редактировать" title="Редактировать" onClick={edit}><Pencil size={16} /></Button>
    <Button variant="ghost" size="icon" aria-label="Удалить" title="Удалить" onClick={remove}><Trash2 size={16} /></Button>
  </div>
}

export function Monitors() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('newest')
  const [offset, setOffset] = useState(0)
  const [editor, setEditor] = useState<Monitor | 'new' | null>(null)
  const [removing, setRemoving] = useState<Monitor | null>(null)
  const { user } = useSession()
  const size = 15
  const params = new URLSearchParams({ limit: String(size), offset: String(offset), sort })
  if (search.trim()) params.set('search', search.trim())
  if (status) params.set('status', status)
  const query = useData<Monitor[]>('/monitors?' + params)
  const action = useMonitorAction()
  return <>
    <SectionTitle title="Мониторы" detail="Настройте проверки для сайтов, API и других HTTP-сервисов"
      actions={!user?.is_demo && <Button onClick={() => setEditor('new')}><Plus size={18} /> Новый монитор</Button>} />
    <section className="panel">
      <div className="table-toolbar">
        <label className="search"><Search size={17} /><input type="search" aria-label="Поиск мониторов" placeholder="Название или URL"
          value={search} onChange={event => { setSearch(event.target.value); setOffset(0) }} /></label>
        <select aria-label="Статус монитора" value={status} onChange={event => { setStatus(event.target.value); setOffset(0) }}>
          <option value="">Все статусы</option>{(Object.keys(labels) as MonitorStatus[]).map(key => <option key={key} value={key}>{labels[key]}</option>)}
        </select>
        <select aria-label="Сортировка" value={sort} onChange={event => { setSort(event.target.value); setOffset(0) }}>
          <option value="newest">Сначала новые</option><option value="name">По названию</option><option value="status">По статусу</option>
          <option value="uptime">По uptime</option><option value="latency">По времени ответа</option>
          <option value="last_checked">По последней проверке</option><option value="interval">По интервалу</option>
        </select>
      </div>
      {query.isPending ? <Skeleton /> : query.isError ? <ErrorPanel error={query.error} retry={() => void query.refetch()} /> :
        <>
          {query.data.length ? <div className="table-scroll"><table><thead><tr>
            <th scope="col">Ресурс</th><th scope="col">Статус</th><th scope="col">Uptime · 30 дн.</th><th scope="col">Ответ</th>
            <th scope="col">Последняя проверка</th><th scope="col">Интервал</th>{!user?.is_demo && <th scope="col"><span className="sr-only">Действия</span></th>}
          </tr></thead><tbody>{query.data.map(item => <tr key={item.id}>
            <td><Link className="table-link" to={`/app/monitors/${item.id}`}>{item.name}</Link><small className="table-url">{item.url}</small></td>
            <td><Status status={item.status} /></td><td>{percent(item.uptime)}</td><td>{ms(item.last_response_time_ms)}</td>
            <td>{formatDate(item.last_checked_at)}</td><td>{duration(item.interval_seconds)}</td>
            {!user?.is_demo && <td><MonitorActions monitor={item} busy={action.isPending}
              run={value => action.mutate({ id: item.id, action: value })} edit={() => setEditor(item)} remove={() => setRemoving(item)} /></td>}
          </tr>)}</tbody></table></div> :
            <Empty title={search || status || offset ? 'Мониторы не найдены' : 'Пока нет мониторов'}
              detail={search || status ? 'Измените фильтр или поисковый запрос.' : undefined} />}
          <Pagination offset={offset} size={size} count={query.data.length} change={setOffset} />
        </>}
    </section>
    {editor && <MonitorDialog monitor={editor === 'new' ? undefined : editor} close={() => setEditor(null)} />}
    {removing && <Confirm title="Удалить монитор?" detail={`«${removing.name}» и его история проверок будут удалены.`}
      close={() => setRemoving(null)} pending={action.isPending}
      confirm={() => action.mutate({ id: removing.id, action: 'delete' }, { onSuccess: () => { setRemoving(null); setOffset(0) } })} />}
  </>
}

export function MonitorDetail() {
  const { id } = useParams()
  const [window, setWindow] = useState<Window>('24h')
  const [offset, setOffset] = useState(0)
  const [incidentsOffset, setIncidentsOffset] = useState(0)
  const [editor, setEditor] = useState(false)
  const [removing, setRemoving] = useState(false)
  const { user } = useSession()
  const navigate = useNavigate()
  const size = 15
  const prefix = '/monitors/' + id
  const detail = useData<Monitor>(prefix)
  const stats = useData<Stats>(prefix + '/stats?window=' + window)
  const checks = useData<Check[]>(prefix + `/checks?limit=${size}&offset=${offset}`)
  const incidents = useData<Incident[]>(prefix + `/incidents?limit=${size}&offset=${incidentsOffset}`)
  const action = useMonitorAction()
  if (detail.isPending) return <Skeleton />
  if (detail.isError) return <ErrorPanel error={detail.error} retry={() => void detail.refetch()} />
  const monitor = detail.data
  const metric = stats.data
  const metrics = [
    ['Среднее', ms(metric?.average_ms)], ['Минимум', ms(metric?.min_ms)], ['Максимум', ms(metric?.max_ms)], ['P95', ms(metric?.p95_ms)],
  ]
  return <>
    <Link className="text-back" to="/app/monitors"><ChevronLeft size={17} /> Мониторы</Link>
    <SectionTitle title={monitor.name} detail={monitor.url} actions={!user?.is_demo && <MonitorActions monitor={monitor}
      busy={action.isPending} run={value => action.mutate({ id: monitor.id, action: value })}
      edit={() => setEditor(true)} remove={() => setRemoving(true)} />} />
    <div className="monitor-meta"><Status status={monitor.status} /><span><Clock3 size={15} /> Каждые {duration(monitor.interval_seconds)}</span>
      <span><Activity size={15} /> Последняя проверка {formatDate(monitor.last_checked_at)}</span></div>
    {stats.isPending ? <Skeleton /> : stats.isError ? <ErrorPanel error={stats.error} retry={() => void stats.refetch()} /> :
      <div className="metrics-grid">
        {windows.map(period => <article className="metric" key={period.value}><div>Uptime · {period.label}</div>
          <strong>{percent(metric?.uptime_windows[period.value])}</strong><small>Доля успешных проверок</small></article>)}
        <article className="metric"><div>Инциденты за период</div><strong>{metric?.incident_count}</strong>
          <small>Суммарный простой {duration(metric?.incident_seconds ?? null)}</small></article>
      </div>}
    <section className="panel separated"><header className="panel-heading">
      <div><h2><Activity size={18} /> Время ответа</h2><p>Проверок за период: {metric?.checks ?? '—'}</p></div>
      <WindowSwitch value={window} change={setWindow} />
    </header>
      <div className="stat-line">{metrics.map(([label, value]) => <div key={label}><span>{label}</span><b>{value}</b></div>)}</div>
      {stats.isPending ? <Skeleton /> : stats.isError ? <ErrorPanel error={stats.error} /> :
        <LatencyChart points={stats.data.series} window={window} id="monitor-latency" />}
    </section>
    <section className="panel separated"><header className="panel-heading"><div><h2><ShieldCheck size={18} /> TLS-сертификат</h2></div></header>
      <div className="stat-line">
        <div><span>Валидность</span><b>{monitor.ssl_valid === null ? 'Нет данных' : monitor.ssl_valid ? 'Валиден' : 'Ошибка проверки'}</b></div>
        <div><span>Имя хоста</span><b>{monitor.ssl_hostname_valid === null ? 'Нет данных' : monitor.ssl_hostname_valid ? 'Совпадает' : 'Не совпадает'}</b></div>
        <div><span>Действует до</span><b>{formatDate(monitor.ssl_expires_at)}</b></div>
        <div><span>Осталось дней</span><b>{monitor.ssl_expires_at ? Math.max(0, Math.ceil((Date.parse(monitor.ssl_expires_at) - Date.now()) / 86_400_000)) : '—'}</b></div>
      </div>
    </section>
    <section className="panel separated"><header className="panel-heading"><div><h2><Globe size={18} /> История проверок</h2></div></header>
      {checks.isPending ? <Skeleton /> : checks.isError ? <ErrorPanel error={checks.error} retry={() => void checks.refetch()} /> :
        <>{checks.data.length ? <div className="table-scroll"><table><thead><tr><th>Время</th><th>Статус</th><th>HTTP</th><th>Ответ</th><th>Причина</th></tr></thead>
          <tbody>{checks.data.map(check => <tr key={check.id}><td>{formatDate(check.checked_at)}</td><td><Status status={check.status} /></td>
            <td>{check.http_status_code ?? '—'}</td><td>{ms(check.response_time_ms)}</td><td>{check.error_message ?? '—'}</td></tr>)}</tbody></table></div> :
          <Empty title="Проверок пока нет" />}
          <Pagination offset={offset} size={size} count={checks.data.length} change={setOffset} /></>}
    </section>
    <section className="panel separated"><header className="panel-heading"><div><h2>История инцидентов</h2></div></header>
      {incidents.isPending ? <Skeleton /> : incidents.isError ? <ErrorPanel error={incidents.error} /> : <>
        <IncidentTable rows={incidents.data} />
        <Pagination offset={incidentsOffset} size={size} count={incidents.data.length} change={setIncidentsOffset} />
      </>}
    </section>
    {editor && <MonitorDialog monitor={monitor} close={() => setEditor(false)} />}
    {removing && <Confirm title="Удалить монитор?" detail="История проверок этого ресурса будет удалена."
      close={() => setRemoving(false)} pending={action.isPending}
      confirm={() => action.mutate({ id: monitor.id, action: 'delete' }, { onSuccess: () => navigate('/app/monitors', { replace: true }) })} />}
  </>
}
