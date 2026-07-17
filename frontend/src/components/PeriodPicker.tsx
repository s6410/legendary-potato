import { formatMonth, shiftMonth } from '../lib/format'

interface Props {
  month: string
  onChange: (month: string) => void
  className?: string
}

/** Månadsväljare med pilar och "idag"-genväg. */
export function PeriodPicker({ month, onChange, className = '' }: Props) {
  const now = new Date().toISOString().slice(0, 7)
  return (
    <div className={`flex items-center gap-1 ${className}`}>
      <button
        onClick={() => onChange(shiftMonth(month, -1))}
        className="rounded-lg border border-baseline px-2.5 py-1.5 text-sm hover:bg-grid"
        aria-label="Föregående månad"
      >
        ←
      </button>
      <span className="min-w-32 px-2 text-center text-sm font-medium capitalize">
        {formatMonth(month, true)}
      </span>
      <button
        onClick={() => onChange(shiftMonth(month, 1))}
        disabled={month >= now}
        className="rounded-lg border border-baseline px-2.5 py-1.5 text-sm hover:bg-grid disabled:opacity-40"
        aria-label="Nästa månad"
      >
        →
      </button>
      {month !== now && (
        <button
          onClick={() => onChange(now)}
          className="ml-1 rounded-lg border border-baseline px-2.5 py-1.5 text-xs text-ink-2 hover:bg-grid"
        >
          Nu
        </button>
      )}
    </div>
  )
}
