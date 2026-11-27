import { createContext, useContext, useState, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { Button } from '../components/ui/button'
import { ToastIcon } from '../components/ui'

type Toast = { id: number; text: string; error: boolean }
const Context = createContext<(text: string, error?: boolean) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Toast[]>([])
  const dismiss = (id: number) => setMessages(current => current.filter(message => message.id !== id))
  function show(text: string, error = false) {
    const id = Date.now() + Math.random()
    setMessages(current => [...current.slice(-3), { id, text, error }])
    window.setTimeout(() => dismiss(id), 5200)
  }
  return <Context.Provider value={show}>{children}<div className="toast-area" aria-live="polite">
    {messages.map(message => <div className={`toast ${message.error ? 'toast-error' : ''}`} key={message.id}>
      <ToastIcon error={message.error} /><span>{message.text}</span>
      <Button size="icon" variant="ghost" aria-label="Закрыть уведомление" onClick={() => dismiss(message.id)}><X size={15} /></Button>
    </div>)}
  </div></Context.Provider>
}

export const useToast = () => useContext(Context)
