import { useState } from 'react'
import { Activity, CheckCircle2, ExternalLink, Pencil, Plus, Radio, Trash2 } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'
import { api } from '../api/client'
import type { Monitor, PageInput, PublicPage, StatusPage } from '../api/types'
import { Brand, Confirm, Empty, ErrorPanel, IncidentStatus, SectionTitle, Skeleton, Status, SyntheticNotice, formatDate, percent } from '../components/ui'
import { Button } from '../components/ui/button'
import { Dialog } from '../components/ui/dialog'
import { useAction, useData } from '../hooks/data'
import { useSession } from '../hooks/session'

const schema = z.object({
  title: z.string().trim().min(1, 'Введите название').max(100),
  slug: z.string().min(2).max(80).regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, 'Используйте латинские буквы, цифры и дефисы'),
  description: z.string().max(500),
  is_public: z.boolean(),
  monitor_ids: z.array(z.string()),
})

function PageEditor({ page, close }: { page?: StatusPage; close: () => void }) {
  const monitors = useData<Monitor[]>('/monitors?limit=200&sort=name')
  const save = useAction((body: PageInput) => api<StatusPage>(page ? `/status-pages/${page.id}` : '/status-pages', {
    method: page ? 'PATCH' : 'POST', body,
  }), 'Статус-страница сохранена', ['/status-pages', '/public/status'])
  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm({
    resolver: zodResolver(schema), defaultValues: page ?? { title: '', slug: '', description: '', is_public: false, monitor_ids: [] },
  })
  const selected = watch('monitor_ids')
  return <Dialog open onClose={close} title={page ? 'Настройки статус-страницы' : 'Новая статус-страница'}
    description="В публичном представлении отображаются имена, состояние и история выбранных сервисов.">
    <form className="dialog-form" onSubmit={handleSubmit(values => save.mutate(schema.parse(values), { onSuccess: close }))} noValidate>
      <label>Название<input {...register('title')} placeholder="Состояние сервисов" />
        {errors.title && <small className="field-error">{errors.title.message}</small>}</label>
      <label>Адрес страницы<input {...register('slug')} placeholder="my-company" />
        {errors.slug && <small className="field-error">{errors.slug.message}</small>}</label>
      <label>Описание<textarea rows={3} {...register('description')} />
        {errors.description && <small className="field-error">{errors.description.message}</small>}</label>
      <fieldset><legend>Сервисы</legend>
        {monitors.isPending ? <Skeleton rows={1} /> : monitors.isError ? <ErrorPanel error={monitors.error} /> :
          !monitors.data.length ? <p className="muted">Сначала добавьте хотя бы один монитор.</p> :
          <div className="checkbox-list">{monitors.data.map(monitor => <label className="checkbox" key={monitor.id}>
            <input type="checkbox" checked={selected.includes(monitor.id)} onChange={event => setValue(
              'monitor_ids', event.target.checked ? [...selected, monitor.id] : selected.filter(id => id !== monitor.id),
            )} /> {monitor.name}
          </label>)}</div>}
      </fieldset>
      <label className="checkbox"><input type="checkbox" {...register('is_public')} /> Опубликовать страницу</label>
      {save.isError && <p className="field-error" role="alert">{save.error.message}</p>}
      <div className="form-actions"><Button variant="secondary" onClick={close}>Отмена</Button>
        <Button type="submit" disabled={save.isPending || monitors.isPending || monitors.isError}>{save.isPending ? 'Сохранение…' : 'Сохранить'}</Button></div>
    </form>
  </Dialog>
}

export function StatusPages() {
  const [editor, setEditor] = useState<StatusPage | 'new' | null>(null)
  const [deleting, setDeleting] = useState<StatusPage | null>(null)
  const { user } = useSession()
  const query = useData<StatusPage[]>('/status-pages')
  const destroy = useAction((id: string) => api('/status-pages/' + id, { method: 'DELETE' }), 'Страница удалена', ['/status-pages', '/public/status'])
  return <>
    <SectionTitle title="Статус-страницы" detail="Делитесь доступностью выбранных сервисов"
      actions={!user?.is_demo && <Button onClick={() => setEditor('new')}><Plus size={18} /> Новая страница</Button>} />
    <section className="panel">
      {query.isPending ? <Skeleton /> : query.isError ? <ErrorPanel error={query.error} retry={() => void query.refetch()} /> :
        !query.data.length ? <Empty icon={Radio} title="Статус-страниц пока нет" detail="Создайте страницу и выберите сервисы для публикации." /> :
          <div className="compact-list page-list">{query.data.map(page => <div key={page.id}>
            <div><strong>{page.title}</strong><small>/status/{page.slug} · Сервисов: {page.monitor_ids.length}</small></div>
            <span className={`status-label status-${page.is_public ? 'up' : 'paused'}`}><i />{page.is_public ? 'Опубликована' : 'Черновик'}</span>
            <div className="inline-actions">
              {page.is_public && <Button asChild size="icon" variant="ghost" aria-label="Открыть публичную страницу">
                <Link to={`/status/${page.slug}`}><ExternalLink size={16} /></Link></Button>}
              {!user?.is_demo && <>
                <Button size="icon" variant="ghost" aria-label="Редактировать" onClick={() => setEditor(page)}><Pencil size={16} /></Button>
                <Button size="icon" variant="ghost" aria-label="Удалить" onClick={() => setDeleting(page)}><Trash2 size={16} /></Button>
              </>}
            </div>
          </div>)}</div>}
    </section>
    {editor && <PageEditor page={editor === 'new' ? undefined : editor} close={() => setEditor(null)} />}
    {deleting && <Confirm title="Удалить статус-страницу?" detail={`Публичный адрес «${deleting.title}» перестанет открываться.`}
      close={() => setDeleting(null)} pending={destroy.isPending} confirm={() => destroy.mutate(deleting.id, { onSuccess: () => setDeleting(null) })} />}
  </>
}

const overallText = {
  up: 'Все сервисы работают', down: 'Часть сервисов недоступна', degraded: 'Часть сервисов работает медленнее',
  pending: 'Ожидаем результатов проверок', paused: 'Мониторинг приостановлен',
}

export function PublicStatus() {
  const { slug } = useParams()
  const query = useData<PublicPage>('/public/status/' + encodeURIComponent(slug ?? ''), { anonymous: true })
  const data = query.data
  return <div className="public-page">
    <header><Brand /><span>Статус сервисов</span></header>
    <main>
      {query.isPending ? <Skeleton /> : query.isError ? <ErrorPanel error={query.error} retry={() => void query.refetch()} /> : data && <>
        <SectionTitle title={data.title} detail={data.description} />
        {data.synthetic && <SyntheticNotice />}
        <div className={`public-overall public-${data.overall}`}>
          {data.overall === 'up' ? <CheckCircle2 size={27} /> : <Activity size={27} />}
          <div><strong>{overallText[data.overall]}</strong><span>Обновлено {formatDate(data.updated_at)}</span></div>
        </div>
        <section className="panel separated"><header className="panel-heading"><div><h2>Сервисы</h2><p>Uptime за 30 дней по результатам проверок</p></div></header>
          {!data.monitors.length ? <Empty title="Сервисы ещё не опубликованы" /> :
            <div className="compact-list public-list">{data.monitors.map(monitor => <div key={monitor.id}>
              <strong>{monitor.name}</strong><Status status={monitor.status} /><span>{percent(monitor.uptime)}</span>
            </div>)}</div>}
        </section>
        <section className="panel separated"><header className="panel-heading"><div><h2>История инцидентов</h2></div></header>
          {!data.incidents.length ? <Empty icon={CheckCircle2} title="Инцидентов нет" /> :
            <div className="compact-list">{data.incidents.map(row => <div key={row.id}>
              <div><strong>{row.monitor_name}</strong><small>{formatDate(row.started_at)}{row.resolved_at && ' · ' + formatDate(row.resolved_at)}</small></div>
              <IncidentStatus status={row.status} />
            </div>)}</div>}
        </section>
      </>}
    </main>
  </div>
}
