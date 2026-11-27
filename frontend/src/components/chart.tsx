import { Activity } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Point, Window } from '../api/types'
import { Empty, ms, percent } from './ui'

export const windows: { value: Window; label: string }[] = [
  { value: '24h', label: '24 часа' }, { value: '7d', label: '7 дней' }, { value: '30d', label: '30 дней' },
]

export function WindowSwitch({ value, change }: { value: Window; change: (value: Window) => void }) {
  return <div className="segments" role="group" aria-label="Период">
    {windows.map(tab => <button key={tab.value} type="button" aria-pressed={value === tab.value}
      onClick={() => change(tab.value)}>{tab.label}</button>)}
  </div>
}

export function CheckChart({ points, window, id, metric = 'latency' }: {
  points: Point[]; window: Window; id: string; metric?: 'latency' | 'availability'
}) {
  const availability = metric === 'availability'
  if (!points.some(point => point.value != null)) return <Empty icon={Activity} title="Недостаточно данных"
    detail={availability ? 'График появится после первой завершённой проверки.' : 'График появится после первой успешной проверки.'} />
  const color = availability ? 'var(--success)' : '#8b87ff'
  const axis = new Intl.DateTimeFormat('ru', window === '24h' ? { hour: '2-digit', minute: '2-digit' } : { day: 'numeric', month: 'short' })
  const tooltip = new Intl.DateTimeFormat('ru', { dateStyle: 'short', timeStyle: 'short' })
  return <div className="check-chart" role="img" aria-label={availability ? 'График доступности' : 'График среднего времени ответа'}>
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={points} margin={{ top: 8, right: 15, bottom: 5, left: 0 }}>
        <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.36} /><stop offset="100%" stopColor={color} stopOpacity={0.02} />
        </linearGradient></defs>
        <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 5" />
        <XAxis dataKey="time" tickFormatter={value => axis.format(new Date(value))} minTickGap={30} axisLine={false} tickLine={false}
          tick={{ fill: 'var(--muted)', fontSize: 11 }} />
        <YAxis width={52} tickFormatter={value => value + (availability ? '%' : ' мс')} domain={[0, availability ? 100 : 'auto']} allowDecimals={false}
          axisLine={false} tickLine={false} tick={{ fill: 'var(--muted)', fontSize: 11 }} />
        <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
          labelFormatter={value => tooltip.format(new Date(String(value)))}
          formatter={value => availability ? [percent(Number(value)), 'Доступность'] : [ms(Number(value)), 'Среднее']} />
        <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill={`url(#${id})`} dot={{ r: 1.5 }}
          activeDot={{ r: 5 }} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  </div>
}
