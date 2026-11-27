import { useState } from 'react'
import { Bell, LockKeyhole, Send, Shield, UserRound } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api, setSession } from '../api/client'
import type { Channel, EventType, NotificationLog, TelegramConnection, User } from '../api/types'
import { Confirm, Empty, ErrorPanel, Pagination, SectionTitle, Skeleton, formatDate } from '../components/ui'
import { Button } from '../components/ui/button'
import { useAction, useData } from '../hooks/data'
import { useSession } from '../hooks/session'

const profileSchema = z.object({ name: z.string().trim().min(1, 'Введите имя').max(80) })
const passwordSchema = z.object({
  current_password: z.string().min(1, 'Введите текущий пароль').max(256),
  new_password: z.string().min(8, 'Минимум 8 символов').max(256),
})

export function Profile() {
  const { user, update } = useSession()
  const navigate = useNavigate()
  const profile = useForm({ resolver: zodResolver(profileSchema), defaultValues: { name: user?.name ?? '' } })
  const password = useForm({ resolver: zodResolver(passwordSchema), defaultValues: { current_password: '', new_password: '' } })
  const save = useAction((body: z.infer<typeof profileSchema>) => api<User>('/profile', { method: 'PATCH', body }), 'Профиль обновлён', [])
  const change = useAction((body: z.infer<typeof passwordSchema>) => api('/profile/change-password', { method: 'POST', body }),
    'Пароль изменён. Войдите снова.', [])
  return <>
    <SectionTitle title="Профиль" detail="Имя аккаунта и настройки входа" />
    <section className="panel settings-panel">
      <header className="panel-heading"><div><h2><UserRound size={18} /> Аккаунт</h2></div></header>
      <form onSubmit={profile.handleSubmit(body => save.mutate(body, { onSuccess: update }))} noValidate>
        <label>Email<input value={user?.email ?? ''} readOnly /></label>
        <label>Имя<input disabled={user?.is_demo} {...profile.register('name')} />
          {profile.formState.errors.name && <small className="field-error">{profile.formState.errors.name.message}</small>}</label>
        {!user?.is_demo && <div><Button type="submit" disabled={save.isPending}>Сохранить</Button></div>}
      </form>
    </section>
    {!user?.is_demo && <section className="panel settings-panel separated">
      <header className="panel-heading"><div><h2><LockKeyhole size={18} /> Изменение пароля</h2>
        <p>После смены пароля потребуется войти заново на всех устройствах.</p></div></header>
      <form onSubmit={password.handleSubmit(body => change.mutate(body, { onSuccess: () => {
        setSession(null); navigate('/login', { replace: true })
      } }))} noValidate>
        <label>Текущий пароль<input autoComplete="current-password" type="password" {...password.register('current_password')} />
          {password.formState.errors.current_password && <small className="field-error">{password.formState.errors.current_password.message}</small>}</label>
        <label>Новый пароль<input autoComplete="new-password" type="password" {...password.register('new_password')} />
          {password.formState.errors.new_password && <small className="field-error">{password.formState.errors.new_password.message}</small>}</label>
        <div><Button type="submit" disabled={change.isPending}>Изменить пароль</Button></div>
      </form>
    </section>}
  </>
}

const eventNames: Record<EventType | 'test', string> = {
  down: 'Недоступность', recovered: 'Восстановление', ssl: 'Истечение TLS-сертификата', test: 'Тестовое уведомление',
}
const delivery = { pending: 'В очереди', sending: 'Отправляется', failed: 'Ошибка', sent: 'Отправлено' }
const notificationKeys = ['/notifications']

function ChannelSettings({ channel, disabled }: { channel: Channel; disabled: boolean }) {
  const [active, setActive] = useState(channel.is_active)
  const [events, setEvents] = useState(channel.events)
  const [removing, setRemoving] = useState(false)
  const path = '/notifications/channels/' + channel.id
  const save = useAction(() => api<Channel>(path, { method: 'PATCH', body: { is_active: active, events } }), 'Уведомления обновлены', notificationKeys)
  const test = useAction(() => api(path + '/test', { method: 'POST' }), 'Тестовое сообщение отправлено', notificationKeys)
  const remove = useAction(() => api(path, { method: 'DELETE' }), 'Telegram отключён', notificationKeys)
  return <form onSubmit={event => { event.preventDefault(); save.mutate(undefined) }}>
    <label className="checkbox"><input type="checkbox" checked={active} onChange={event => setActive(event.target.checked)} disabled={disabled} /> Уведомления включены</label>
    <fieldset disabled={disabled}><legend>Типы событий</legend>
      {(Object.keys(eventNames) as (EventType | 'test')[]).filter(key => key !== 'test').map(key =>
        <label className="checkbox" key={key}><input type="checkbox" checked={events.includes(key)} onChange={event => {
          setEvents(event.target.checked ? [...events, key] : events.filter(value => value !== key))
        }} /> {eventNames[key]}</label>)}
    </fieldset>
    {!disabled && <div className="form-actions align-start">
      <Button type="submit" disabled={save.isPending}>Сохранить</Button>
      <Button variant="secondary" disabled={test.isPending || !channel.is_active} onClick={() => test.mutate(undefined)}><Send size={16} /> Отправить тест</Button>
      <Button variant="ghost" onClick={() => setRemoving(true)}>Отключить</Button>
    </div>}
    {removing && <Confirm title="Отключить Telegram?" detail="Чтобы восстановить доставку, понадобится заново подключить бота."
      close={() => setRemoving(false)} pending={remove.isPending}
      confirm={() => remove.mutate(undefined, { onSuccess: () => setRemoving(false) })} />}
  </form>
}

export function Notifications() {
  const [offset, setOffset] = useState(0)
  const { user } = useSession()
  const connection = useData<TelegramConnection>('/notifications/telegram/status', { interval: 5000 })
  const events = useData<NotificationLog[]>(`/notifications/logs?limit=15&offset=${offset}`)
  const connect = useAction(() => api<{ url: string; expires_at: string }>('/notifications/telegram/connect', { method: 'POST' }),
    'Одноразовая ссылка создана', notificationKeys)
  const channel = connection.data?.channel
  return <>
    <SectionTitle title="Уведомления" detail="Доставка событий мониторинга и история отправки" />
    <section className="panel settings-panel">
      <header className="panel-heading"><div><h2><Send size={18} /> Telegram</h2><p>{channel ? 'Аккаунт подключён' : 'Подключите аккаунт через личный чат с ботом.'}</p></div></header>
      {connection.isPending ? <Skeleton /> : connection.isError ? <ErrorPanel error={connection.error} retry={() => void connection.refetch()} /> :
        channel ? <ChannelSettings channel={channel} disabled={!!user?.is_demo || !connection.data.configured} /> :
        !connection.data.configured ? <Empty icon={Bell} title="Канал ещё не настроен" detail="Для подключения нужны токен и имя Telegram-бота в настройках приложения." /> :
        <div className="settings-body">
          {!user?.is_demo && <Button disabled={connect.isPending} onClick={() => connect.mutate(undefined)}>Создать ссылку подключения</Button>}
          {connect.data && <div className="connection-link">
            <Button asChild variant="secondary"><a href={connect.data.url} target="_blank" rel="noreferrer">Открыть бота в Telegram</a></Button>
            <p>Нажмите «Запустить» в личном чате. Ссылка действует до {formatDate(connect.data.expires_at)}.</p>
          </div>}
        </div>}
    </section>
    <section className="panel separated"><header className="panel-heading"><div><h2>История доставки</h2></div></header>
      {events.isPending ? <Skeleton /> : events.isError ? <ErrorPanel error={events.error} /> : <>
        {!events.data.length ? <Empty icon={Bell} title="Уведомлений пока нет" /> :
          <div className="table-scroll"><table><thead><tr><th>Событие</th><th>Состояние</th><th>Время</th><th>Подробности</th></tr></thead>
            <tbody>{events.data.map(row => <tr key={row.id}><td>{eventNames[row.event_type]}</td><td>{delivery[row.status]}</td>
              <td>{formatDate(row.created_at)}</td><td>{row.error_message ?? '—'}</td></tr>)}</tbody></table></div>}
        <Pagination size={15} offset={offset} count={events.data.length} change={setOffset} />
      </>}
    </section>
  </>
}

function AdminContent() {
  const [offset, setOffset] = useState(0)
  const [target, setTarget] = useState<User | null>(null)
  const users = useData<User[]>(`/admin/users?limit=20&offset=${offset}`)
  const stats = useData<{ users: number; monitors: number; reserved: number; running: number }>('/admin/stats')
  const change = useAction((user: User) => api<User>(`/admin/users/${user.id}`, { method: 'PATCH', body: { is_active: !user.is_active } }),
    'Статус аккаунта обновлён', ['/admin'])
  const labels = { users: 'Пользователи', monitors: 'Мониторы', reserved: 'Проверки зарезервированы', running: 'Проверки выполняются' }
  return <>
    <SectionTitle title="Администрирование" detail="Пользователи и состояние фоновых проверок" />
    {stats.isPending ? <Skeleton /> : stats.isError ? <ErrorPanel error={stats.error} /> :
      <div className="metrics-grid">{(Object.keys(labels) as (keyof typeof labels)[]).map(key =>
        <article className="metric" key={key}><div>{labels[key]}</div><strong>{stats.data[key]}</strong></article>)}</div>}
    <section className="panel separated">
      {users.isPending ? <Skeleton /> : users.isError ? <ErrorPanel error={users.error} /> : <>
        <div className="table-scroll"><table><thead><tr><th>Имя</th><th>Email</th><th>Роль</th><th>Статус</th><th>Действия</th></tr></thead>
          <tbody>{users.data.map(user => <tr key={user.id}><td>{user.name}</td><td>{user.email}</td>
            <td>{user.role === 'admin' ? 'Администратор' : 'Пользователь'}</td><td>{user.is_active ? 'Активен' : 'Заблокирован'}</td>
            <td>{user.role !== 'admin' && <Button variant="secondary" size="small" onClick={() => setTarget(user)}>
              {user.is_active ? 'Заблокировать' : 'Разблокировать'}</Button>}</td></tr>)}</tbody></table></div>
        <Pagination size={20} offset={offset} count={users.data.length} change={setOffset} />
      </>}
    </section>
    {target && <Confirm title={target.is_active ? 'Заблокировать аккаунт?' : 'Разблокировать аккаунт?'}
      detail={target.email} close={() => setTarget(null)} pending={change.isPending}
      confirm={() => change.mutate(target, { onSuccess: () => setTarget(null) })} />}
  </>
}

export function AdminPage() {
  const { user } = useSession()
  return user?.role === 'admin' ? <AdminContent /> : <Empty icon={Shield} title="Требуются права администратора" />
}
