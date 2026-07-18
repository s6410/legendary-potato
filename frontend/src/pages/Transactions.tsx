import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api, useAccounts, useApiMutation, useMembers, useTransactions } from '../api/hooks'
import type { Txn } from '../api/types'
import { AmountText } from '../components/AmountText'
import { CategoryPicker } from '../components/CategoryPicker'
import { EmptyState } from '../components/EmptyState'
import { Modal } from '../components/Modal'
import { formatDate, formatOre } from '../lib/format'

export function TransactionsPage() {
  const [params, setParams] = useSearchParams()
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [categorizing, setCategorizing] = useState<Txn[] | null>(null)
  const [settingMember, setSettingMember] = useState<number[] | null>(null)
  const [page, setPage] = useState(1)

  const filters = useMemo(() => {
    const f: Record<string, unknown> = { page, page_size: 100 }
    for (const key of ['from', 'to', 'account_id', 'category_id', 'q', 'member'] as const) {
      const v = params.get(key)
      if (v) f[key] = v
    }
    if (params.get('uncategorized') === '1') f.uncategorized = true
    return f
  }, [params, page])

  const { data, isLoading } = useTransactions(filters)
  const { data: accounts = [] } = useAccounts()
  const { data: members = [] } = useMembers()

  function setFilter(key: string, value: string | null) {
    setPage(1)
    setSelected(new Set())
    setParams(
      (prev) => {
        if (value) prev.set(key, value)
        else prev.delete(key)
        return prev
      },
      { replace: true },
    )
  }

  const rows = data?.rows ?? []
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id))
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  const exportUrl = useMemo(() => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(filters)) {
      if (k !== 'page' && k !== 'page_size' && v) qs.set(k, String(v))
    }
    return `/api/transactions/export.csv?${qs.toString()}`
  }, [filters])

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Transaktioner</h1>
        <a
          href={exportUrl}
          className="rounded-lg border border-baseline px-3 py-1.5 text-sm hover:bg-grid"
        >
          Exportera CSV
        </a>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          type="search"
          placeholder="Sök beskrivning …"
          key={params.get('q') ?? ''}
          defaultValue={params.get('q') ?? ''}
          onKeyDown={(e) => {
            if (e.key === 'Enter') setFilter('q', (e.target as HTMLInputElement).value || null)
          }}
          className="w-56"
        />
        <select
          value={params.get('account_id') ?? ''}
          onChange={(e) => setFilter('account_id', e.target.value || null)}
        >
          <option value="">Alla konton</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
        <CategoryPicker
          value={params.get('category_id') ? Number(params.get('category_id')) : null}
          onChange={(id) => setFilter('category_id', id ? String(id) : null)}
        />
        <input
          type="date"
          value={params.get('from') ?? ''}
          onChange={(e) => setFilter('from', e.target.value || null)}
          aria-label="Från datum"
        />
        <input
          type="date"
          value={params.get('to') ?? ''}
          onChange={(e) => setFilter('to', e.target.value || null)}
          aria-label="Till datum"
        />
        {members.length > 0 && (
          <select
            value={params.get('member') ?? ''}
            onChange={(e) => setFilter('member', e.target.value || null)}
            aria-label="Medlem"
          >
            <option value="">Alla medlemmar</option>
            {members.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
            <option value="__none__">Utan medlem</option>
          </select>
        )}
        <label className="flex items-center gap-1.5 text-sm text-ink-2">
          <input
            type="checkbox"
            checked={params.get('uncategorized') === '1'}
            onChange={(e) => setFilter('uncategorized', e.target.checked ? '1' : null)}
            className="h-4 w-4"
          />
          Endast okategoriserade
        </label>
        {[...params.keys()].length > 0 && (
          <button
            onClick={() => {
              setPage(1)
              setParams({}, { replace: true })
            }}
            className="text-sm text-accent hover:underline"
          >
            Rensa filter
          </button>
        )}
      </div>

      {selected.size > 0 && (
        <div className="mb-3 flex items-center gap-3 rounded-lg bg-accent/10 px-4 py-2.5 text-sm">
          <span className="font-medium">{selected.size} markerade</span>
          <button
            onClick={() => setCategorizing(rows.filter((r) => selected.has(r.id)))}
            className="rounded-lg bg-accent px-3 py-1.5 font-medium text-white hover:opacity-90"
          >
            Kategorisera …
          </button>
          <button
            onClick={() => setSettingMember([...selected])}
            className="rounded-lg border border-baseline px-3 py-1.5 hover:bg-grid"
          >
            Sätt medlem …
          </button>
          <button onClick={() => setSelected(new Set())} className="text-ink-2 hover:underline">
            Avmarkera
          </button>
        </div>
      )}

      {!isLoading && rows.length === 0 ? (
        <EmptyState
          icon="🧾"
          title="Inga transaktioner ännu"
          actionLabel="Importera din första fil"
          actionTo="/import"
        >
          Importera en CSV- eller Excel-export från din bank så dyker transaktionerna upp här.
        </EmptyState>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-bord text-left text-xs text-muted">
                <th className="w-8 px-3 py-2.5">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={(e) =>
                      setSelected(e.target.checked ? new Set(rows.map((r) => r.id)) : new Set())
                    }
                    aria-label="Markera alla"
                    className="h-4 w-4"
                  />
                </th>
                <th className="px-3 py-2.5">Datum</th>
                <th className="px-3 py-2.5">Beskrivning</th>
                <th className="px-3 py-2.5">Konto</th>
                <th className="px-3 py-2.5">Kategori</th>
                <th className="px-3 py-2.5 text-right">Belopp</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <TxnRow
                  key={t.id}
                  txn={t}
                  selected={selected.has(t.id)}
                  onSelect={(on) =>
                    setSelected((prev) => {
                      const next = new Set(prev)
                      if (on) next.add(t.id)
                      else next.delete(t.id)
                      return next
                    })
                  }
                  onCategorize={() => setCategorizing([t])}
                />
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between border-t border-bord px-4 py-2.5 text-sm text-ink-2">
            <span>
              {data?.total ?? 0} transaktioner · netto {formatOre(data?.total_amount_ore ?? 0)}
            </span>
            {totalPages > 1 && (
              <span className="flex items-center gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                  className="rounded border border-baseline px-2 py-1 disabled:opacity-40"
                >
                  ←
                </button>
                Sida {page} av {totalPages}
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  className="rounded border border-baseline px-2 py-1 disabled:opacity-40"
                >
                  →
                </button>
              </span>
            )}
          </div>
        </div>
      )}

      {categorizing && (
        <CategorizeDialog
          txns={categorizing}
          onClose={() => {
            setCategorizing(null)
            setSelected(new Set())
          }}
        />
      )}
      {settingMember && (
        <MemberDialog
          ids={settingMember}
          members={members}
          onClose={() => {
            setSettingMember(null)
            setSelected(new Set())
          }}
        />
      )}
    </div>
  )
}

function MemberDialog({
  ids,
  members,
  onClose,
}: {
  ids: number[]
  members: string[]
  onClose: () => void
}) {
  const [choice, setChoice] = useState<string>(members[0] ?? '')
  const [custom, setCustom] = useState('')
  const mutation = useApiMutation(
    () =>
      api.send('POST', '/transactions/bulk-member', {
        ids,
        member: choice === '__custom__' ? custom.trim() : choice === '__none__' ? null : choice,
      }),
    onClose,
  )
  const valid = choice === '__none__' || (choice === '__custom__' ? custom.trim() !== '' : choice !== '')
  return (
    <Modal title={`Sätt medlem för ${ids.length} transaktioner`} onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <select value={choice} onChange={(e) => setChoice(e.target.value)}>
          {members.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
          <option value="__custom__">+ Ny medlem …</option>
          <option value="__none__">(rensa medlem)</option>
        </select>
        {choice === '__custom__' && (
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="Namn, t.ex. Anna"
            autoFocus
          />
        )}
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

function TxnRow({
  txn,
  selected,
  onSelect,
  onCategorize,
}: {
  txn: Txn
  selected: boolean
  onSelect: (on: boolean) => void
  onCategorize: () => void
}) {
  const linkBadge =
    txn.link &&
    (txn.link.kind === 'refund' ? (
      <span title="Del av återbetalningspar" className="text-xs">
        ⇄
      </span>
    ) : (
      <span title="Kontoöverföring" className="text-xs">
        ⇅
      </span>
    ))
  return (
    <tr className={`border-b border-bord/50 last:border-0 hover:bg-grid/40 ${txn.is_excluded ? 'opacity-50' : ''}`}>
      <td className="px-3 py-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={(e) => onSelect(e.target.checked)}
          aria-label="Markera rad"
          className="h-4 w-4"
        />
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-ink-2">{formatDate(txn.booked_date)}</td>
      <td className="max-w-md px-3 py-2">
        <span className="block truncate">
          {txn.description} {linkBadge}
          {txn.member && (
            <span className="ml-1.5 rounded-full bg-series-7/15 px-1.5 py-0.5 text-xs text-ink-2">
              {txn.member}
            </span>
          )}
        </span>
        {txn.note && <span className="block truncate text-xs text-muted">{txn.note}</span>}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-xs text-ink-2">{txn.account_name}</td>
      <td className="whitespace-nowrap px-3 py-2">
        <button
          onClick={onCategorize}
          className={`rounded-full px-2.5 py-1 text-xs transition-colors ${
            txn.category_path
              ? 'bg-grid text-ink-2 hover:bg-baseline/50'
              : 'bg-series-4/15 font-medium hover:bg-series-4/25'
          }`}
          title={txn.category_source === 'rule' ? 'Kategoriserad av regel' : undefined}
        >
          {txn.category_path ?? 'Kategorisera'}
          {txn.category_source === 'rule' && ' ⚙'}
        </button>
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-right">
        <AmountText ore={txn.amount_ore} decimals />
      </td>
    </tr>
  )
}

function CategorizeDialog({ txns, onClose }: { txns: Txn[]; onClose: () => void }) {
  const [categoryId, setCategoryId] = useState<number | null>(txns[0].category_id)
  const [createRule, setCreateRule] = useState(txns.length === 1)
  const [matchType, setMatchType] = useState<'exact' | 'prefix' | 'contains'>('exact')
  const [pattern, setPattern] = useState(txns[0].description_norm)
  const [result, setResult] = useState<{ categorized: number; others_affected: number } | null>(null)

  const mutation = useApiMutation(
    (body: object) => api.send<{ categorized: number; others_affected: number }>('POST', '/transactions/bulk-categorize', body),
    (r) => setResult(r),
  )

  if (result) {
    return (
      <Modal title="Kategoriserat" onClose={onClose}>
        <p className="text-sm text-ink-2">
          {result.categorized} transaktion{result.categorized !== 1 && 'er'} kategoriserades.
          {result.others_affected > 0 &&
            ` Regeln kategoriserade dessutom ${result.others_affected} andra transaktioner automatiskt.`}
        </p>
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
    <Modal
      title={txns.length === 1 ? 'Kategorisera transaktion' : `Kategorisera ${txns.length} transaktioner`}
      onClose={onClose}
    >
      <div className="mb-3 max-h-32 overflow-y-auto rounded-lg bg-grid/40 px-3 py-2 text-sm">
        {txns.slice(0, 6).map((t) => (
          <div key={t.id} className="flex justify-between gap-3">
            <span className="truncate">{t.description}</span>
            <AmountText ore={t.amount_ore} className="shrink-0" />
          </div>
        ))}
        {txns.length > 6 && <div className="text-xs text-muted">… och {txns.length - 6} till</div>}
      </div>

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Kategori</span>
        <CategoryPicker value={categoryId} onChange={setCategoryId} allowEmpty={false} emptyLabel="" />
      </label>

      <label className="mt-4 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={createRule}
          onChange={(e) => setCreateRule(e.target.checked)}
          className="h-4 w-4"
        />
        <span>Skapa regel så att liknande transaktioner kategoriseras automatiskt</span>
      </label>

      {createRule && (
        <div className="mt-3 flex flex-col gap-2 rounded-lg border border-bord p-3 text-sm">
          <div className="flex gap-2">
            <select
              value={matchType}
              onChange={(e) => setMatchType(e.target.value as typeof matchType)}
            >
              <option value="exact">Exakt lika</option>
              <option value="prefix">Börjar med</option>
              <option value="contains">Innehåller</option>
            </select>
            <input
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              className="flex-1"
              placeholder="mönster"
            />
          </div>
          <span className="text-xs text-muted">
            Matchas mot den normaliserade beskrivningen (utan kortnummer och datum). Tips: korta
            ner mönstret och välj "Börjar med" för att träffa alla butiker i kedjan.
          </span>
        </div>
      )}

      {mutation.isError && (
        <div className="mt-3 text-sm text-bad">{(mutation.error as Error).message}</div>
      )}

      <div className="mt-5 flex justify-end gap-3">
        <button
          onClick={onClose}
          className="rounded-lg border border-baseline px-4 py-2 text-sm hover:bg-grid"
        >
          Avbryt
        </button>
        <button
          disabled={!categoryId || mutation.isPending || (createRule && !pattern.trim())}
          onClick={() =>
            mutation.mutate({
              ids: txns.map((t) => t.id),
              category_id: categoryId,
              rule: createRule ? { match_type: matchType, pattern } : null,
            })
          }
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          Spara
        </button>
      </div>
    </Modal>
  )
}
