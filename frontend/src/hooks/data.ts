import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useToast } from './toast'

export function useData<T>(path: string, options: { interval?: number; anonymous?: boolean } = {}) {
  return useQuery({
    queryKey: [path],
    queryFn: ({ signal }) => api<T>(path, { ...options, signal }),
    refetchInterval: options.interval ?? 30_000,
  })
}

export function useAction<T, Input>(action: (input: Input) => Promise<T>, message: string, refresh: string[]) {
  const cache = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: action,
    onSuccess: async () => {
      toast(message)
      await Promise.all(refresh.map(prefix => cache.invalidateQueries({
        predicate: query => String(query.queryKey[0]).startsWith(prefix),
      })))
    },
    onError: error => toast(error.message, true),
  })
}
