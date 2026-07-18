import { useState } from 'react'

import { api, useApiMutation, useRebalance } from '../../api/hooks'
import type { SavingsAccount, SavingsPlanAccount } from '../../api/types'
import { formatDate, formatOre, parseKr } from '../../lib/format'
import { Modal } from '../Modal'

interface PlanCardProps {
  accounts: SavingsAccount[]
  planAccounts: SavingsPlanAccount[]
}

/** Månadssparande: aktiva sparplaner med månadens köpförslag per innehav. */
export function PlanCard({ accounts, planAccounts }: PlanCardProps) {
  const [editing, setEditing] = useState<SavingsPlanAccount | 'new' | null>(null)
  const topLevel = accounts.filter((a) => a.parent_id == null)
  const planless = topLevel.filter((a) => !planAccounts.some((p) => p.id === a.id))

  return (
    <div className="card mb-5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Månadssparande</h2>
        {planAccounts.length > 0 && planless.length > 0 && (
          <button onClick={() => setEditing('new')} className="text-sm text-accent hover:underline">
            + Plan för fler konton
          </button>
        )}
      </div>

      {planAccounts.length === 0 ? (
        <div className="mt-3 text-sm text-ink-2">
          <p>
            Ange hur mycket du sätter in varje månad, så följer appen insatt kapital mot
            avkastning och föreslår hur beloppet bör fördelas mellan fonderna.
          </p>
          <button
            onClick={() => setEditing('new')}
            disabled={topLevel.length === 0}
            className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Starta månadssparande
          </button>
        </div>
      ) : (
        <div className="mt-3 flex flex-col gap-5">
          {planAccounts.map((p) => (
            <PlanRow key={p.id} plan={p} onEdit={() => setEditing(p)} />
          ))}
        </div>
      )}

      {editing && (
        <PlanDialog
          topLevel={editing === 'new' ? planless : topLevel}
          existing={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

function PlanRow({ plan, onEdit }: { plan: SavingsPlanAccount; onEdit: () => void }) {
  const { data: buyPlan } = useRebalance(plan.monthly_amount_ore, plan.id)
  const endPlan = useApiMutation(() => api.send('DELETE', `/savings/accounts/${plan.id}/plan`))
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>
          <strong>{formatOre(plan.monthly_amount_ore)}/mån</strong> till {plan.name}
          <span className="text-muted"> · sedan {formatDate(plan.start_date)}</span>
        </span>
        <span className="flex gap-3">
          <button onClick={onEdit} className="text-accent hover:underline">
            Ändra
          </button>
          <button
            onClick={() => {
              if (confirm(`Avsluta månadssparandet till ${plan.name}? Historiken behålls.`))
                endPlan.mutate(undefined)
            }}
            className="text-muted hover:text-bad"
          >
            Avsluta
          </button>
        </span>
      </div>
      <div className="mt-1.5 text-sm">
        {buyPlan && buyPlan.allocations.length > 0 ? (
          <ul className="flex flex-col gap-1">
            {buyPlan.allocations.map((a) => (
              <li key={a.id ?? a.label} className="flex justify-between">
                <span className="text-ink-2">{a.label}</span>
                <span className="tabular font-medium">{formatOre(a.amount_ore)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted">Hela beloppet sätts in på kontot.</p>
        )}
      </div>
    </div>
  )
}

function PlanDialog({
  topLevel,
  existing,
  onClose,
}: {
  topLevel: SavingsAccount[]
  existing: SavingsPlanAccount | null
  onClose: () => void
}) {
  const [accountId, setAccountId] = useState<number | undefined>(existing?.id ?? topLevel[0]?.id)
  const [amountText, setAmountText] = useState(
    existing ? String(existing.monthly_amount_ore / 100) : '5000',
  )
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10))
  const amountOre = parseKr(amountText)
  const mutation = useApiMutation(
    () =>
      api.send('PUT', `/savings/accounts/${accountId}/plan`, {
        monthly_amount_ore: amountOre,
        start_date: startDate,
      }),
    onClose,
  )
  return (
    <Modal
      title={existing ? `Ändra månadssparande — ${existing.name}` : 'Starta månadssparande'}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3 text-sm">
        {!existing && (
          <label className="flex flex-col gap-1">
            <span className="font-medium">Konto</span>
            <select value={accountId} onChange={(e) => setAccountId(Number(e.target.value))}>
              {topLevel.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1">
          <span className="font-medium">Belopp per månad (kr)</span>
          <input
            inputMode="decimal"
            value={amountText}
            onChange={(e) => setAmountText(e.target.value)}
            autoFocus
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium">Startdatum</span>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          <span className="text-xs text-muted">
            Kontots nuvarande värde räknas som startkapital. Månadsbeloppet fördelas enligt
            kontots målfördelning.
          </span>
        </label>
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={mutation.isPending || accountId == null || amountOre == null || amountOre <= 0}
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
