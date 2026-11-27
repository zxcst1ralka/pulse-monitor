import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { refreshSession, subscribe } from '../api/client'
import type { User } from '../api/types'

const Auth = createContext<{ user: User | null; loading: boolean; update: (user: User) => void } | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const queries = useQueryClient()

  useEffect(() => {
    let previous: string | undefined
    const unsubscribe = subscribe(next => {
      if (previous && previous !== next?.id) queries.clear()
      previous = next?.id
      setUser(next)
    })
    if (/^\/app(?:\/|$)/.test(window.location.pathname)) {
      void refreshSession().catch(() => null).finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
    return unsubscribe
  }, [queries])

  return <Auth.Provider value={{ user, loading, update: setUser }}>{children}</Auth.Provider>
}

export function useSession() {
  const value = useContext(Auth)
  if (!value) throw new Error('SessionProvider is missing')
  return value
}
