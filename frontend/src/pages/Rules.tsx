import { useState } from 'react'

import { api, useApiMutation, useRules } from '../api/hooks'
import type { Rule } from '../api/types'
import { CategoryPicker } from '../components/CategoryPicker'
import { EmptyState } from '../components/EmptyState'
import { Modal } from '../components/Modal'

const TYPE_LABELS: Record<string, string> = {
  exact: 'Exakt lika',
  prefix: 'Börjar med',
  contains: 'Innehåller',
}

export function RulesPage() {
  const { data: rules = [], isLoading } = useRules()
  const [editing, setEditing] = useState<Rule | null>(null)
  const [creating, setCreating] = useState(false)
  const [applyResult, setApplyResult] = useState<number | null>(null)

  const applyAll = useApiMutation(
    () => api.send<{ affected: number }>('POST', '/rules/apply-all'),
    (r) => setApplyResult(r.affected),
  )
  const deleteRule = useApiMutation((id: number) => api.send('DELETE', `/rules/${id}`))

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Kategoriseringsregler</h1>
        <div className="flex gap-2">
          <button
            onClick={() => applyAll.mutate(undefined)}
            disabled={applyAll.isPending}
            className="rounded-lg border border-baseline px-3 py-1.5 text-sm hover:bg-grid disabled:opacity-50"
          >
            Kör om alla regler
          </button>
          <button
            onClick={() => setCreating(true)}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
          >
            + Ny regel
          </button>
        </div>
      </div>

      {applyResult !== null && (
        <div className="mb-4 rounded-lg bg-accent/10 px-4 py-2.5 text-sm">
          {applyResult} transaktioner uppdaterades av reglerna.
        </div>
      )}

      <p className="mb-4 text-sm text-ink-2">
        Regler skapas enklast från transaktionslistan när du kategoriserar — de matchar den
        normaliserade beskrivningen (gemener, utan kortnummer och datum) och appliceras automatiskt
        vid varje import. Manuellt satta kategorier skrivs aldrig över.
      </p>

      {!isLoading && rules.length === 0 ? (
        <EmptyState icon="⚙" title="Inga regler ännu" actionLabel="Till transaktionerna" actionTo="/transaktioner">
          Kategorisera en transaktion och kryssa i "Skapa regel" så dyker den upp här.
        </EmptyState>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-bord text-left text-xs text-muted">
                <th className="px-4 py-2.5">Matchning</th>
                <th className="px-4 py-2.5">Mönster</th>
                <th className="px-4 py-2.5">Kategori</th>
                <th className="px-4 py-2.5">Konto</th>
                <th className="px-4 py-2.5 text-right">Träffar</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id} className="border-b border-bord/50 last:border-0 hover:bg-grid/40">
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-ink-2">
                    {TYPE_LABELS[r.match_type]}
                  </td>
                  <td className="max-w-xs truncate px-4 py-2 font-mono text-xs">{r.pattern}</td>
                  <td className="whitespace-nowrap px-4 py-2">{r.category_path}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-ink-2">
                    {r.account_name ?? 'Alla'}
                  </td>
                  <td className="px-4 py-2 text-right tabular">{r.hit_count}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-right text-xs">
                    <button onClick={() => setEditing(r)} className="text-accent hover:underline">
                      ändra
                    </button>
                    <button
                      onClick={() => deleteRule.mutate(r.id)}
                      className="ml-3 text-bad hover:underline"
                    >
                      ta bort
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(editing || creating) && (
        <RuleDialog
          rule={editing}
          onClose={() => {
            setEditing(null)
            setCreating(false)
          }}
        />
      )}
    </div>
  )
}

function RuleDialog({ rule, onClose }: { rule: Rule | null; onClose: () => void }) {
  const [matchType, setMatchType] = useState(rule?.match_type ?? 'contains')
  const [pattern, setPattern] = useState(rule?.pattern ?? '')
  const [categoryId, setCategoryId] = useState<number | null>(rule?.category_id ?? null)
  const [affected, setAffected] = useState<number | null>(null)

  const mutation = useApiMutation(
    () =>
      rule
        ? api.send<{ affected: number }>('PATCH', `/rules/${rule.id}`, {
            match_type: matchType,
            pattern,
            category_id: categoryId,
          })
        : api.send<{ affected: number }>('POST', '/rules', {
            match_type: matchType,
            pattern,
            category_id: categoryId,
          }),
    (r) => setAffected(r.affected ?? 0),
  )

  if (affected !== null) {
    return (
      <Modal title="Regeln sparades" onClose={onClose}>
        <p className="text-sm text-ink-2">{affected} transaktioner (om)kategoriserades av regeln.</p>
        <div className="mt-4 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            Klart
          </button>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title={rule ? 'Ändra regel' : 'Ny regel'} onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <div className="flex gap-2">
          <select value={matchType} onChange={(e) => setMatchType(e.target.value as Rule['match_type'])}>
            {Object.entries(TYPE_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
          <input
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            className="flex-1"
            placeholder="t.ex. ica"
            autoFocus
          />
        </div>
        <label className="flex flex-col gap-1">
          <span className="font-medium">Kategori</span>
          <CategoryPicker value={categoryId} onChange={setCategoryId} allowEmpty={false} emptyLabel="" />
        </label>
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={!pattern.trim() || !categoryId || mutation.isPending}
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
