import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from './button'

export function Dialog({ open, onClose, title, description, children }: {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
}) {
  return <DialogPrimitive.Root open={open} onOpenChange={next => { if (!next) onClose() }}>
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="dialog-overlay" />
      <DialogPrimitive.Content className="dialog-content" {...(description ? {} : { 'aria-describedby': undefined })}>
        <header className="dialog-heading">
          <div><DialogPrimitive.Title>{title}</DialogPrimitive.Title>
            {description && <DialogPrimitive.Description>{description}</DialogPrimitive.Description>}
          </div>
          <DialogPrimitive.Close asChild><Button variant="ghost" size="icon" aria-label="Закрыть"><X size={18} /></Button></DialogPrimitive.Close>
        </header>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  </DialogPrimitive.Root>
}
