import { useState } from 'react'

import { api, useApiMutation, useDeposits } from '../../api/hooks'
import type { SavingsAccount } from '../../api/types'
import { formatDate, formatSigned, parseKr } from '../../lib/format'
import { Modal } from '../Modal'

/** Engångsinsättningar (negativt belopp = uttag) per toppnivåkonto. De räknas
 * in i insatt kapital så att värdeökningen efter en insättning inte tolkas
 * som avkastning. */
export function DepositsDialog({
  accounts,
  onClose,
}: {
  accounts: SavingsAccount[]
  onClose: () => void
}) {
  const topLevel = accounts.filter((a) => a.parent_id == null)
  const [accountId, setAccountId] = useState<number | undefined>(topLevel[0]?.id)
  const { data: deposits = [] } = useDeposits(accountId)

  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [amountText, setAmountText] = useState('')
  const [note, setNote] = useState('')
  const amountOre = parseKr(amountText)

  const add = useApiMutation(
    () =>
      api.send('POST', `/savings/accounts/${accountId}/deposits`, {
        deposit_date: date,
        amount_ore: amountOre,
        note: note.trim() || null,
      }),
    () => {
      setAmountText('')
      setNote('')
    },
  )
  const remove = useApiMutation((id: number) => api.send('DELETE', `/savings/deposits/${id}`))

  return (
    <Modal title="Engångsinsättningar" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <p className="text-xs text-muted">
          Registrera insättningar utanför månadssparandet (negativt belopp = uttag). De räknas
          in i insatt kapital, så att värdeökningen efter en insättning inte visas som
          avkastning.
        </p>
        {topLevel.length > 1 && (
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
        <div className="flex gap-2">
          <label className="flex flex-1 flex-col gap-1">
            <span className="font-medium">Datum</span>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className="font-medium">Belopp (kr)</span>
            <input
              inputMode="decimal"
              placeholder="t.ex. 100 000"
              value={amountText}
              onChange={(e) => setAmountText(e.target.value)}
              autoFocus
            />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className="font-medium">Anteckning (valfri)</span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="t.ex. Flytt från annat konto"
          />
        </label>
        {add.isError && <span className="text-bad">{(add.error as Error).message}</span>}
        <div className="flex justify-end">
          <button
            disabled={add.isPending || accountId == null || !date || amountOre == null || amountOre === 0}
            onClick={() => add.mutate(undefined)}
            className="rounded-lg bg-accent px-4 py-2 font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Lägg till
          </button>
        </div>

        {deposits.length > 0 && (
          <div className="border-t border-bord/50 pt-3">
            <h3 className="mb-1.5 text-xs font-medium text-muted">Registrerade insättningar</h3>
            <ul className="flex flex-col gap-1">
              {deposits.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-3">
                  <span>
                    {formatDate(d.deposit_date)}
                    {d.note && <span className="text-xs text-muted"> · {d.note}</span>}
                  </span>
                  <span className="flex items-center gap-2">
                    <span className={`tabular font-medium ${d.amount_ore < 0 ? 'text-bad' : ''}`}>
                      {formatSigned(d.amount_ore)}
                    </span>
                    <button
                      onClick={() => {
                        if (confirm('Ta bort insättningen?')) remove.mutate(d.id)
                      }}
                      className="text-xs text-muted hover:text-bad"
                      title="Ta bort"
                    >
                      ✕
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-2 flex justify-end">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Stäng
          </button>
        </div>
      </div>
    </Modal>
  )
}
