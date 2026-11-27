import { Slot } from '@radix-ui/react-slot'
import type { ComponentProps } from 'react'

type Props = ComponentProps<'button'> & {
  asChild?: boolean
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'default' | 'small' | 'icon'
}

// Shadcn's Radix Slot pattern with PulseMonitor button tokens.
export function Button({ asChild, variant = 'primary', size = 'default', className = '', type, ...props }: Props) {
  const Component = asChild ? Slot : 'button'
  return <Component className={`button button-${variant} button-${size} ${className}`}
    type={asChild ? undefined : type ?? 'button'} {...props} />
}
