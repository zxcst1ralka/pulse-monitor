import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@fontsource-variable/manrope'
import { ApiError } from './api/client'
import { SessionProvider } from './hooks/session'
import { ToastProvider } from './hooks/toast'
import { App } from './App'
import './styles.css'

document.documentElement.dataset.theme = localStorage.getItem('pulse-theme') === 'light' ? 'light' : 'dark'
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, retry: (count, error) => count < 1 && (!(error instanceof ApiError) || error.status >= 500) } },
})

createRoot(document.getElementById('root')!).render(
  <BrowserRouter><QueryClientProvider client={queryClient}><SessionProvider><ToastProvider>
    <App />
  </ToastProvider></SessionProvider></QueryClientProvider></BrowserRouter>,
)
