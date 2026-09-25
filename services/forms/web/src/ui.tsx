// Minimal shadcn/ui-style primitives (same class recipes as shadcn's Button/Card/Badge).
import type { ButtonHTMLAttributes, HTMLAttributes } from 'react'

const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(' ')

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'outline' | 'ghost' }

export function Button({ variant = 'default', className, ...props }: ButtonProps) {
  return (
    <button
      className={cx(
        'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium h-9 px-4 transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50',
        variant === 'default' && 'bg-primary text-primary-foreground shadow-xs hover:bg-primary/90',
        variant === 'outline' && 'border border-input bg-background shadow-xs hover:bg-accent hover:text-accent-foreground',
        variant === 'ghost' && 'hover:bg-accent hover:text-accent-foreground',
        className,
      )}
      {...props}
    />
  )
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx('rounded-xl border bg-card text-card-foreground shadow-sm', className)} {...props} />
}

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cx('inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium', className)}
      {...props}
    />
  )
}
