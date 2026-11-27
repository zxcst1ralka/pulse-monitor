export type MonitorStatus = 'pending' | 'up' | 'down' | 'degraded' | 'paused'
export type Window = '24h' | '7d' | '30d'
export type EventType = 'down' | 'recovered' | 'ssl'

export interface User {
  id: string
  name: string
  email: string
  role: string
  is_active: boolean
  is_demo: boolean
}

export interface Access {
  access_token: string
  user: User
}

export interface MonitorInput {
  name: string
  url: string
  type: 'http' | 'keyword'
  interval_seconds: number
  timeout_seconds: number
  expected_status_code: number
  keyword: string | null
  response_threshold_ms: number
  notifications_enabled: boolean
}

export interface Monitor extends MonitorInput {
  id: string
  status: MonitorStatus
  is_active: boolean
  is_synthetic: boolean
  last_checked_at: string | null
  next_check_at: string
  last_response_time_ms: number | null
  ssl_expires_at: string | null
  ssl_valid: boolean | null
  ssl_hostname_valid: boolean | null
  uptime?: number | null
}

export interface Check {
  id: string
  status: MonitorStatus
  http_status_code: number | null
  response_time_ms: number | null
  error_message: string | null
  checked_at: string
}

export interface Incident {
  id: string
  monitor_id: string
  monitor_name: string
  status: 'ongoing' | 'resolved'
  reason: string
  http_status_code: number | null
  started_at: string
  resolved_at: string | null
  duration_seconds: number | null
}

export interface Point { time: string; value: number | null }

export interface Metrics {
  checks: number
  successful: number
  uptime: number | null
  average_ms: number | null
  min_ms: number | null
  max_ms: number | null
  p95_ms: number | null
}

export interface Summary extends Metrics {
  total: number
  statuses: Partial<Record<MonitorStatus, number>>
  open_incidents: number
}

export interface Stats extends Metrics {
  series: Point[]
  window: Window
  uptime_windows: Record<Window, number | null>
  incident_count: number
  incident_seconds: number
}

export interface PageInput {
  title: string
  slug: string
  description: string
  is_public: boolean
  monitor_ids: string[]
}

export interface StatusPage extends PageInput {
  id: string
  updated_at: string
}

export interface PublicPage {
  title: string
  description: string
  overall: MonitorStatus
  updated_at: string
  synthetic: boolean
  monitors: { id: string; name: string; status: MonitorStatus; uptime: number | null }[]
  incidents: Pick<Incident, 'id' | 'monitor_name' | 'status' | 'started_at' | 'resolved_at'>[]
}

export interface Channel {
  id: string
  type: string
  is_active: boolean
  events: EventType[]
}

export interface TelegramConnection {
  configured: boolean
  connected: boolean
  channel: Channel | null
}

export interface NotificationLog {
  id: string
  event_type: EventType | 'test'
  status: 'pending' | 'sending' | 'failed' | 'sent'
  error_message: string | null
  created_at: string
}
