import type { EChartsOption } from 'echarts'
import { useMemo, useState } from 'react'

import {
  api,
  useApiMutation,
  useDrift,
  useSavingsAccounts,
  useSavingsHistory,
  useTargets,
} from '../api/hooks'
import type { DriftClass, SavingsAccount } from '../api/types'
import { EChart } from '../components/EChart'
import { Modal } from '../components/Modal'
import { formatDate, formatOre } from '../lib/format'
import { chartTokens, useTheme } from '../lib/theme'

const CLASS_OPTIONS = [
  ['equity', 'Aktier'],
  ['fixed_income', 'Räntor'],
  ['cash', 'Kontanter'],
  ['other', 'Övrigt'],
] as const

const CLASS_COLOR_INDEX: Record<string, number> = {
  equity: 0,
  fixed_income: 4,
  cash: 3,
  other: 6,
}

export function SavingsPage() {
  const { data: accounts = [] } = useSavingsAccounts()
  const { data: history } = useSavingsHistory()
  const { data: drift } = useDrift()
  const { mode } = useTheme()
  const tokens = useMemo(() => chartTokens(), [mode]) // eslint-disable-line react-hooks/exhaustive-deps

  const [entering, setEntering] = useState(false)
  const [addingAccount, setAddingAccount] = useState(false)
  const [editingTargets, setEditingTargets] = useState(false)

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Sparande</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setAddingAccount(true)}
            className="rounded-lg border border-baseline px-3 py-1.5 text-sm hover:bg-grid"
          >
            + Sparkonto
          </button>
          <button
            onClick={() => setEntering(true)}
            disabled={accounts.length === 0}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Uppdatera värden
          </button>
        </div>
      </div>
      <p className="mb-5 text-sm text-ink-2">
        Lägg in dina spar- och investeringskonton, uppdatera värdena när det passar (t.ex.
        månadsvis) och följ utvecklingen och driften mot din målfördelning.
      </p>

      {accounts.length === 0 ? (
        <div className="card px-6 py-12 text-center">
          <div className="text-4xl" aria-hidden>
            ⛁
          </div>
          <h2 className="mt-3 text-lg font-semibold">Inga sparkonton ännu</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-ink-2">
            Skapa t.ex. "ISK Avanza" (Aktier), "Räntefond" (Räntor) och "Buffertkonto" (Kontanter)
            — och mata sedan in aktuella värden.
          </p>
          <button
            onClick={() => setAddingAccount(true)}
            className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            + Lägg till första sparkontot
          </button>
        </div>
      ) : (
        <>
          <div className="card mb-5 flex items-baseline justify-between px-5 py-4">
            <span className="text-sm text-ink-2">Totalt sparande</span>
            <span className="text-3xl font-bold tabular">{formatOre(drift?.total_ore ?? 0)}</span>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div className="card p-4">
              <h2 className="mb-2 font-semibold">Konton</h2>
              <table className="w-full text-sm">
                <tbody>
                  {accounts.map((a) => (
                    <AccountRow key={a.id} account={a} />
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card p-4">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="font-semibold">Fördelning mot mål</h2>
                <button
                  onClick={() => setEditingTargets(true)}
                  className="text-sm text-accent hover:underline"
                >
                  Ändra mål
                </button>
              </div>
              {drift && drift.total_ore > 0 ? (
                <DriftView drift={drift.classes} tokens={tokens} />
              ) : (
                <p className="py-8 text-center text-sm text-muted">
                  Mata in värden så visas fördelningen här.
                </p>
              )}
            </div>
          </div>

          {history && history.dates.length > 1 && (
            <div className="card mt-5 p-4">
              <h2 className="mb-2 font-semibold">Utveckling över tid</h2>
              <EChart height={300} option={historyOption(history, tokens)} />
            </div>
          )}
        </>
      )}

      {entering && <SnapshotDialog accounts={accounts} onClose={() => setEntering(false)} />}
      {addingAccount && <AddAccountDialog onClose={() => setAddingAccount(false)} />}
      {editingTargets && <TargetsDialog onClose={() => setEditingTargets(false)} />}
    </div>
  )
}

function AccountRow({ account }: { account: SavingsAccount }) {
  const remove = useApiMutation((id: number) => api.send('DELETE', `/savings/accounts/${id}`))
  return (
    <tr className="border-b border-bord/50 last:border-0">
      <td className="py-2">
        <div className="font-medium">{account.name}</div>
        <div className="text-xs text-muted">{account.asset_class_label}</div>
      </td>
      <td className="py-2 text-right">
        <div className="tabular font-medium">{formatOre(account.latest_value_ore)}</div>
        {account.latest_date && (
          <div className="text-xs text-muted">per {formatDate(account.latest_date)}</div>
        )}
      </td>
      <td className="w-8 py-2 text-right">
        <button
          onClick={() => {
            if (confirm(`Ta bort ${account.name} och all dess historik?`)) remove.mutate(account.id)
          }}
          className="text-xs text-muted hover:text-bad"
          title="Ta bort"
        >
          ✕
        </button>
      </td>
    </tr>
  )
}

function DriftView({ drift, tokens }: { drift: DriftClass[]; tokens: ReturnType<typeof chartTokens> }) {
  return (
    <div className="flex flex-col gap-3">
      {drift.map((c) => {
        const color = tokens.series[CLASS_COLOR_INDEX[c.asset_class] ?? 6]
        return (
          <div key={c.asset_class}>
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} aria-hidden />
                {c.label}
              </span>
              <span className="tabular text-ink-2">
                {String(c.current_pct).replace('.', ',')} %
                {c.target_pct != null && <span className="text-muted"> / mål {String(c.target_pct).replace('.', ',')} %</span>}
              </span>
            </div>
            <div className="relative mt-1.5 h-2.5 overflow-hidden rounded-full bg-grid">
              <div
                className="h-full rounded-full"
                style={{ width: `${Math.min(100, c.current_pct)}%`, background: color }}
              />
              {c.target_pct != null && (
                <div
                  className="absolute top-0 h-full w-0.5 bg-ink"
                  style={{ left: `${Math.min(100, c.target_pct)}%` }}
                  title={`Mål ${c.target_pct} %`}
                />
              )}
            </div>
            {c.drift_ore != null && Math.abs(c.drift_pct ?? 0) >= 1 && (
              <div className={`mt-1 text-xs ${Math.abs(c.drift_pct ?? 0) >= 5 ? 'text-bad' : 'text-muted'}`}>
                {c.drift_ore > 0 ? 'Övervikt' : 'Undervikt'} {formatOre(Math.abs(c.drift_ore))} (
                {String(Math.abs(c.drift_pct ?? 0)).replace('.', ',')} procentenheter)
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function historyOption(
  history: NonNullable<ReturnType<typeof useSavingsHistory>['data']>,
  t: ReturnType<typeof chartTokens>,
): EChartsOption {
  return {
    textStyle: { color: t.ink2 },
    legend: { textStyle: { color: t.ink2, fontSize: 11 }, top: 0 },
    grid: { left: 8, right: 8, top: 32, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.ink, fontSize: 12 },
      valueFormatter: (v) => (v == null ? '–' : formatOre(Number(v))),
    },
    xAxis: {
      type: 'category',
      data: history.dates,
      axisLine: { lineStyle: { color: t.baseline } },
      axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: t.muted, fontSize: 10, formatter: (v: number) => formatOre(v) },
      splitLine: { lineStyle: { color: t.grid } },
    },
    series: history.series.map((s, i) => ({
      name: s.name,
      type: 'line',
      stack: 'total',
      areaStyle: { opacity: 0.35 },
      lineStyle: { width: 2 },
      symbol: 'circle',
      symbolSize: 5,
      itemStyle: { color: t.series[i % t.series.length] },
      color: t.series[i % t.series.length],
      data: s.values,
      connectNulls: true,
    })),
  }
}

function SnapshotDialog({ accounts, onClose }: { accounts: SavingsAccount[]; onClose: () => void }) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [values, setValues] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      accounts.map((a) => [a.id, a.latest_value_ore != null ? String(a.latest_value_ore / 100) : '']),
    ),
  )
  const mutation = useApiMutation(
    () =>
      api.send('POST', '/savings/snapshots', {
        snapshot_date: date,
        values: accounts
          .filter((a) => values[a.id]?.trim())
          .map((a) => ({
            savings_account_id: a.id,
            value_ore: Math.round(parseFloat(values[a.id].replace(/\s/g, '').replace(',', '.')) * 100),
          })),
      }),
    onClose,
  )
  return (
    <Modal title="Uppdatera värden" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="font-medium">Datum</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        {accounts.map((a) => (
          <label key={a.id} className="flex items-center justify-between gap-3">
            <span>
              {a.name} <span className="text-xs text-muted">({a.asset_class_label})</span>
            </span>
            <input
              inputMode="decimal"
              className="w-36 text-right"
              placeholder="kr"
              value={values[a.id] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [a.id]: e.target.value }))}
            />
          </label>
        ))}
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={mutation.isPending}
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

function AddAccountDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [assetClass, setAssetClass] = useState('equity')
  const mutation = useApiMutation(
    () => api.send('POST', '/savings/accounts', { name: name.trim(), asset_class: assetClass }),
    onClose,
  )
  return (
    <Modal title="Nytt sparkonto" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="font-medium">Namn</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="t.ex. ISK Avanza" autoFocus />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium">Tillgångsslag</span>
          <select value={assetClass} onChange={(e) => setAssetClass(e.target.value)}>
            {CLASS_OPTIONS.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={!name.trim() || mutation.isPending}
            onClick={() => mutation.mutate(undefined)}
            className="rounded-lg bg-accent px-4 py-2 font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Skapa
          </button>
        </div>
      </div>
    </Modal>
  )
}

function TargetsDialog({ onClose }: { onClose: () => void }) {
  const { data: targets = [] } = useTargets()
  const [values, setValues] = useState<Record<string, string> | null>(null)
  const current =
    values ??
    Object.fromEntries(
      CLASS_OPTIONS.map(([k]) => [k, String(targets.find((t) => t.asset_class === k)?.target_pct ?? 0)]),
    )
  const total = Object.values(current).reduce((s, v) => s + (parseFloat(v.replace(',', '.')) || 0), 0)

  const mutation = useApiMutation(
    () =>
      api.send('PUT', '/savings/targets', {
        targets: Object.entries(current)
          .filter(([, v]) => (parseFloat(v.replace(',', '.')) || 0) > 0)
          .map(([asset_class, v]) => ({ asset_class, target_pct: parseFloat(v.replace(',', '.')) })),
      }),
    onClose,
  )
  return (
    <Modal title="Målfördelning" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        {CLASS_OPTIONS.map(([k, label]) => (
          <label key={k} className="flex items-center justify-between gap-3">
            <span>{label}</span>
            <span className="flex items-center gap-1">
              <input
                inputMode="decimal"
                className="w-20 text-right"
                value={current[k]}
                onChange={(e) => setValues({ ...current, [k]: e.target.value })}
              />
              %
            </span>
          </label>
        ))}
        <div className={`text-right text-xs ${Math.abs(total - 100) > 1 ? 'text-bad' : 'text-muted'}`}>
          Summa: {String(Math.round(total * 10) / 10).replace('.', ',')} % (ska bli 100 %)
        </div>
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={mutation.isPending || Math.abs(total - 100) > 1}
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
