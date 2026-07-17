import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface Props {
  icon?: string
  title: string
  children?: ReactNode
  actionLabel?: string
  actionTo?: string
}

export function EmptyState({ icon = '📭', title, children, actionLabel, actionTo }: Props) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center">
      <div className="text-4xl" aria-hidden>
        {icon}
      </div>
      <h2 className="text-lg font-semibold">{title}</h2>
      {children && <p className="max-w-md text-sm text-ink-2">{children}</p>}
      {actionLabel && actionTo && (
        <Link
          to={actionTo}
          className="mt-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          {actionLabel}
        </Link>
      )}
    </div>
  )
}
