import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api, useApiMutation, useBudgets, useForecast } from '../api/hooks'
import { CategoryPicker } from '../components/CategoryPicker'
import { Modal } from '../components/Modal'
import { PeriodPicker } from '../components/PeriodPicker'
import { currentMonth, formatOre } from '../lib/format'

export function BudgetPage() {
  const [month, setMonth] = useState(currentMonth())
  const { data } = useBudgets(month)
  const { data: forecast } = useForecast()
  const [adding, setAdding] = useState(false)

  const items = data?.items ?? []
  const totalBudget = items.reduce((s, i) => s + i.budget_ore, 0)
  const totalSpent = items.reduce((s, i) => s + i.spent_ore, 0)
  const deleteBudget = useApiMutation((id: number) => api.send('DELETE', `/budgets/${id}`))

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Budget</h1>
        <div className="flex items-center gap-3">
          <PeriodPicker month={month} onChange={setMonth} />
          <button
            onClick={() => setAdding(true)}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
          >
            + Budgetpost
          </button>
        </div>
      </div>

      {items.length > 0 && (
        <div className="card mb-4 flex items-center justify-between px-5 py-3 text-sm">
          <span className="text-ink-2">Totalt budgeterat</span>
          <span className="tabular">
            <strong>{formatOre(totalSpent)}</strong> av {formatOre(totalBudget)}
          </span>
        </div>
      )}

      {items.length === 0 ? (
        <div className="card px-6 py-12 text-center">
          <div className="text-4xl" aria-hidden>
            ◔
          </div>
          <h2 className="mt-3 text-lg font-semibold">Ingen budget satt ännu</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-ink-2">
            Sätt månadsbudgetar per kategori och följ utfallet här.
            {forecast && forecast.categories.length > 0 && (
              <> Tips: prognosen nedan visar vad kategorierna brukar kosta — bra utgångsvärden.</>
            )}
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {items.map((item) => {
            const pct = Math.min(1.5, item.progress ?? 0)
            const over = (item.progress ?? 0) > 1
            const near = !over && (item.progress ?? 0) > 0.85
            return (
              <div key={item.budget_id} className="card p-4">
                <div className="flex items-center justify-between text-sm">
                  <Link
                    to={`/transaktioner?category_id=${item.category_id}&from=${month}-01`}
                    className="font-medium hover:text-accent"
                  >
                    {item.category_path}
                  </Link>
                  <span className="flex items-center gap-3">
                    <span className="tabular text-ink-2">
                      {formatOre(item.spent_ore)} / {formatOre(item.budget_ore)}
                    </span>
                    <button
                      onClick={() => deleteBudget.mutate(item.budget_id)}
                      className="text-xs text-muted hover:text-bad"
                      title="Ta bort budgetposten"
                    >
                      ✕
                    </button>
                  </span>
                </div>
                <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-grid">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, pct * 100)}%`,
                      background: over ? 'var(--bad)' : near ? 'var(--series-4)' : (item.color ?? 'var(--accent)'),
                    }}
                  />
                </div>
                <div className="mt-1 flex justify-between text-xs text-muted">
                  <span>
                    {over
                      ? `${formatOre(-item.remaining_ore)} över budget`
                      : `${formatOre(item.remaining_ore)} kvar`}
                  </span>
                  <span>{Math.round((item.progress ?? 0) * 100)} %</span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {forecast && forecast.categories.length > 0 && (
        <div className="card mt-6 p-5">
          <h2 className="font-semibold">Vad kategorierna brukar kosta</h2>
          <p className="mt-1 text-xs text-muted">
            Trimmat snitt över senaste sex månaderna ({forecast.based_on_months[0]} –{' '}
            {forecast.based_on_months.at(-1)}). Totalt ≈{' '}
            {formatOre(Math.abs(forecast.projected_total_monthly_ore))}/månad.
          </p>
          <ul className="mt-3 grid gap-1.5 text-sm sm:grid-cols-2">
            {forecast.categories.slice(0, 12).map((c) => (
              <li key={String(c.category_id)} className="flex justify-between gap-3">
                <span className="truncate text-ink-2">{c.name}</span>
                <span className="tabular">{formatOre(Math.abs(c.projected_monthly_ore))}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {adding && <AddBudgetDialog month={month} onClose={() => setAdding(false)} />}
    </div>
  )
}

function AddBudgetDialog({ month, onClose }: { month: string; onClose: () => void }) {
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [amount, setAmount] = useState('')
  const mutation = useApiMutation(
    () =>
      api.send('POST', '/budgets', {
        category_id: categoryId,
        amount_ore: Math.round(parseFloat(amount.replace(',', '.')) * 100),
        valid_from: month,
      }),
    onClose,
  )
  const valid = categoryId != null && parseFloat(amount.replace(',', '.')) > 0
  return (
    <Modal title="Ny budgetpost" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="font-medium">Kategori</span>
          <CategoryPicker value={categoryId} onChange={setCategoryId} allowEmpty={false} emptyLabel="" kinds={['expense']} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium">Månadsbudget (kr)</span>
          <input
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="t.ex. 6000"
            autoFocus
          />
        </label>
        <p className="text-xs text-muted">
          Gäller från {month} och framåt tills du sätter ett nytt värde.
        </p>
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={!valid || mutation.isPending}
            onClick={() => mutation.mutate(undefined)}
            className="rounded-lg bg-accent px-4 py-2 font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Spara
          </button>
        </div>
      </div>
    </Modal>
  )
}
