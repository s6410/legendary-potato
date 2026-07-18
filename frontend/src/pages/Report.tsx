import { Link, useNavigate, useParams } from 'react-router-dom'

import { useMonthlyReport } from '../api/hooks'
import { AmountText } from '../components/AmountText'
import { PeriodPicker } from '../components/PeriodPicker'
import { currentMonth, formatDate, formatMonth, formatOre, formatPct } from '../lib/format'

export function ReportPage() {
  const params = useParams()
  const navigate = useNavigate()
  const month = params.month ?? currentMonth()
  const { data: report, isLoading } = useMonthlyReport(month)

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <h1 className="text-2xl font-bold">Månadsrapport</h1>
        <div className="flex items-center gap-3">
          <PeriodPicker month={month} onChange={(m) => navigate(`/rapport/${m}`)} />
          <Link
            to={`/rapport/ar/${month.slice(0, 4)}`}
            className="rounded-lg border border-baseline px-3 py-1.5 text-sm hover:bg-grid"
          >
            Årsrapport {month.slice(0, 4)}
          </Link>
          <button
            onClick={() => window.print()}
            className="rounded-lg border border-baseline px-3 py-1.5 text-sm hover:bg-grid"
          >
            Skriv ut
          </button>
        </div>
      </div>

      {isLoading || !report ? (
        <div className="py-16 text-center text-muted">Laddar …</div>
      ) : (
        <div className="flex flex-col gap-5">
          <div className="card p-5">
            <h2 className="text-lg font-semibold capitalize">{formatMonth(month, true)}</h2>
            <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="Inkomster" value={formatOre(report.summary.income_ore)} />
              <Stat label="Utgifter" value={formatOre(report.summary.expenses_ore)} />
              <Stat label="Netto" value={formatOre(report.summary.net_ore)} />
              <Stat
                label="Sparkvot"
                value={report.summary.savings_rate != null ? formatPct(report.summary.savings_rate) : '–'}
              />
            </div>
            <p className="mt-3 text-sm text-ink-2">
              Jämfört med {formatMonth(prevOf(month))}: utgifterna{' '}
              {diffText(report.summary.expenses_ore, report.previous_summary.expenses_ore, true)},
              inkomsterna {diffText(report.summary.income_ore, report.previous_summary.income_ore, false)}.
            </p>
          </div>

          <div className="card p-5">
            <h2 className="mb-3 font-semibold">Utgifter per kategori</h2>
            <CategoryBars
              buckets={report.by_category.filter((b) => b.kind === 'expense' && b.amount_ore < 0)}
            />
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div className="card p-5">
              <h2 className="mb-3 font-semibold">Största enskilda utgifter</h2>
              <ul className="flex flex-col gap-1.5 text-sm">
                {report.largest_expenses.slice(0, 8).map((t) => (
                  <li key={t.id} className="flex justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate">{t.description}</span>
                      <span className="text-xs text-muted">
                        {formatDate(t.booked_date)} · {t.category_path ?? 'Okategoriserad'}
                      </span>
                    </span>
                    <AmountText ore={t.amount_ore} className="shrink-0" />
                  </li>
                ))}
              </ul>
            </div>

            <div className="card p-5">
              <h2 className="mb-3 font-semibold">Största utgiftsställen</h2>
              <ul className="flex flex-col gap-1.5 text-sm">
                {report.top_merchants.map((m) => (
                  <li key={m.description_norm} className="flex justify-between gap-3">
                    <span className="truncate">
                      {m.merchant}
                      <span className="ml-1 text-xs text-muted">×{m.transaction_count}</span>
                    </span>
                    <AmountText ore={m.amount_ore} className="shrink-0" />
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {report.budget.length > 0 && (
            <div className="card p-5">
              <h2 className="mb-3 font-semibold">Budgetutfall</h2>
              <ul className="flex flex-col gap-2 text-sm">
                {report.budget.map((b) => (
                  <li key={b.budget_id}>
                    <div className="flex justify-between">
                      <span>{b.category_path}</span>
                      <span className="tabular text-ink-2">
                        {formatOre(b.spent_ore)} / {formatOre(b.budget_ore)}
                      </span>
                    </div>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-grid">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.min(100, (b.progress ?? 0) * 100)}%`,
                          background: (b.progress ?? 0) > 1 ? 'var(--bad)' : (b.color ?? 'var(--accent)'),
                        }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {report.upcoming_recurring.length > 0 && (
            <div className="card p-5">
              <h2 className="mb-3 font-semibold">Kommande återkommande dragningar</h2>
              <ul className="flex flex-col gap-1.5 text-sm">
                {report.upcoming_recurring.map((r) => (
                  <li key={`${r.description_norm}-${r.account_id}`} className="flex justify-between gap-3">
                    <span className="truncate">
                      {r.display_name}
                      <span className="ml-1 text-xs text-muted">({r.cadence_label.toLowerCase()})</span>
                    </span>
                    <span className="shrink-0 text-ink-2">
                      ~{formatDate(r.next_expected_date)} · {formatOre(r.median_amount_ore)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className="mt-0.5 text-xl font-semibold tabular">{value}</div>
    </div>
  )
}

function CategoryBars({ buckets }: { buckets: { name: string; color: string | null; amount_ore: number }[] }) {
  const max = Math.max(...buckets.map((b) => Math.abs(b.amount_ore)), 1)
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {buckets.map((b) => (
        <li key={b.name}>
          <div className="flex justify-between">
            <span>{b.name}</span>
            <span className="tabular text-ink-2">{formatOre(Math.abs(b.amount_ore))}</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-grid">
            <div
              className="h-full rounded-full"
              style={{
                width: `${(Math.abs(b.amount_ore) / max) * 100}%`,
                background: b.color ?? 'var(--accent)',
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}

function prevOf(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, '0')}`
}

function diffText(current: number, previous: number, isExpense: boolean): string {
  const diff = Math.abs(current) - Math.abs(previous)
  if (previous === 0) return 'saknar jämförelse'
  const dir = diff > 0 ? (isExpense ? 'ökade' : 'ökade') : 'minskade'
  return `${dir} med ${formatOre(Math.abs(diff))}`
}
