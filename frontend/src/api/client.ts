import type { Access, User } from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let session: Access | null = null
let refreshRequest: Promise<Access | null> | null = null
const subscribers = new Set<(user: User | null) => void>()

export function setSession(value: Access | null) {
  session = value
  subscribers.forEach(callback => callback(value?.user ?? null))
}

export function subscribe(callback: (user: User | null) => void) {
  subscribers.add(callback)
  return () => { subscribers.delete(callback) }
}

type Options = Omit<RequestInit, 'body'> & { body?: unknown; anonymous?: boolean }

async function request<T>(path: string, { body, anonymous, headers, ...options }: Options = {}): Promise<T> {
  const requestHeaders = new Headers(headers)
  if (body !== undefined) requestHeaders.set('Content-Type', 'application/json')
  if (!anonymous && session) requestHeaders.set('Authorization', 'Bearer ' + session.access_token)
  let response: Response
  try {
    response = await fetch('/api/v1' + path, {
      ...options, credentials: 'same-origin', headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'Не удалось связаться с PulseMonitor')
  }
  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = response.status === 429 ? 'Слишком много запросов. Попробуйте позже.' : 'Сервис временно недоступен'
    throw new ApiError(response.status, typeof data?.detail === 'string' ? data.detail : message)
  }
  return data as T
}

async function withSessionLock<T>(operation: () => Promise<T>): Promise<T> {
  return navigator.locks ? await navigator.locks.request('pulse-monitor-session', operation) : await operation()
}

export function refreshSession(): Promise<Access | null> {
  if (!refreshRequest) {
    refreshRequest = withSessionLock(async () => {
      try {
        const value = await request<Access>('/auth/refresh', { method: 'POST', anonymous: true })
        setSession(value)
        return value
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          setSession(null)
          return null
        }
        throw error
      }
    }).finally(() => { refreshRequest = null })
  }
  return refreshRequest
}

export async function authenticate(path: '/auth/login' | '/auth/register', body: unknown) {
  return withSessionLock(async () => {
    const value = await request<Access>(path, { method: 'POST', body, anonymous: true })
    setSession(value)
    return value.user
  })
}

export function signOut() {
  return withSessionLock(async () => {
    await request('/auth/logout', { method: 'POST', anonymous: true })
    setSession(null)
  })
}

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const attempted = session?.access_token
  try {
    return await request<T>(path, options)
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401 || options.anonymous || !attempted) throw error
    if (session?.access_token === attempted && !await refreshSession()) throw error
    if (!session) throw error
    return request<T>(path, options)
  }
}
