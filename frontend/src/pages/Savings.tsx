import type { EChartsOption } from 'echarts'
import { useMemo, useState } from 'react'

import {
  api,
  useApiMutation,
  useDrift,
  useRebalance,
  useSavingsAccounts,
  useSavingsHistory,
} from '../api/hooks'
import type { Drift, DriftAccountSection, SavingsAccount } from '../api/types'
import { EChart } from '../components/EChart'
import {
  AddAccountDialog,
  AddHoldingDialog,
  HoldingTargetsDialog,
  SnapshotDialog,
  TargetsDialog,
} from '../components/savings/dialogs'
import { formatDate, formatOre, formatSigned, parseKr } from '../lib/format'
import { chartTokens, useTheme } from '../lib/theme'

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
  const [addingHoldingTo, setAddingHoldingTo] = useState<SavingsAccount | null>(null)
  const [editingTargets, setEditingTargets] = useState(false)

  const topLevel = accounts.filter((a) => a.parent_id == null)
  const holdingsOf = (id: number) => accounts.filter((a) => a.parent_id === id)

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
                  {topLevel.map((a) => (
                    <AccountGroup
                      key={a.id}
                      account={a}
                      holdings={holdingsOf(a.id)}
                      onAddHolding={() => setAddingHoldingTo(a)}
                    />
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
                <DriftView
                  rows={drift.classes.map((c) => ({
                    key: c.asset_class,
                    label: c.label,
                    color: tokens.series[CLASS_COLOR_INDEX[c.asset_class] ?? 6],
                    current_pct: c.current_pct,
                    target_pct: c.target_pct,
                    drift_pct: c.drift_pct,
                    drift_ore: c.drift_ore,
                  }))}
                />
              ) : (
                <p className="py-8 text-center text-sm text-muted">
                  Mata in värden så visas fördelningen här.
                </p>
              )}
            </div>
          </div>

          {drift && drift.accounts.length > 0 && drift.total_ore > 0 && (
            <HoldingsDriftCard sections={drift.accounts} tokens={tokens} />
          )}

          {drift && drift.total_ore > 0 && <RebalanceCard drift={drift} />}

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
      {addingHoldingTo && (
        <AddHoldingDialog parent={addingHoldingTo} onClose={() => setAddingHoldingTo(null)} />
      )}
      {editingTargets && <TargetsDialog onClose={() => setEditingTargets(false)} />}
    </div>
  )
}

function AccountGroup({
  account,
  holdings,
  onAddHolding,
}: {
  account: SavingsAccount
  holdings: SavingsAccount[]
  onAddHolding: () => void
}) {
  const remove = useApiMutation((id: number) => api.send('DELETE', `/savings/accounts/${id}`))
  const confirmText =
    holdings.length > 0
      ? `Ta bort ${account.name} med ${holdings.length} innehav och all historik?`
      : `Ta bort ${account.name} och all dess historik?`
  return (
    <>
      <tr className="border-b border-bord/50 last:border-0">
        <td className="py-2">
          <div className="font-medium">{account.name}</div>
          <div className="text-xs text-muted">
            {holdings.length > 0 ? `${holdings.length} innehav` : account.asset_class_label}
            {' · '}
            <button onClick={onAddHolding} className="text-accent hover:underline">
              + innehav
            </button>
          </div>
        </td>
        <td className="py-2 text-right align-top">
          <div className="tabular font-medium">{formatOre(account.latest_value_ore)}</div>
          {account.latest_date && (
            <div className="text-xs text-muted">per {formatDate(account.latest_date)}</div>
          )}
        </td>
        <td className="w-8 py-2 text-right align-top">
          <button
            onClick={() => {
              if (confirm(confirmText)) remove.mutate(account.id)
            }}
            className="text-xs text-muted hover:text-bad"
            title="Ta bort"
          >
            ✕
          </button>
        </td>
      </tr>
      {holdings.map((h) => (
        <HoldingRow key={h.id} holding={h} />
      ))}
    </>
  )
}

function HoldingRow({ holding }: { holding: SavingsAccount }) {
  const remove = useApiMutation((id: number) => api.send('DELETE', `/savings/accounts/${id}`))
  return (
    <tr className="border-b border-bord/50 last:border-0">
      <td className="py-1.5 pl-5">
        <div className="text-sm">{holding.name}</div>
        <div className="text-xs text-muted">
          {holding.asset_class_label}
          {holding.target_pct != null &&
            ` · mål ${String(holding.target_pct).replace('.', ',')} %`}
        </div>
      </td>
      <td className="py-1.5 text-right align-top">
        <div className="tabular text-sm">{formatOre(holding.latest_value_ore)}</div>
      </td>
      <td className="w-8 py-1.5 text-right align-top">
        <button
          onClick={() => {
            if (confirm(`Ta bort innehavet ${holding.name} och dess historik?`))
              remove.mutate(holding.id)
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

interface DriftRow {
  key: string | number
  label: string
  color: string
  current_pct: number
  target_pct: number | null
  drift_pct: number | null
  drift_ore: number | null
}

function DriftView({ rows }: { rows: DriftRow[] }) {
  return (
    <div className="flex flex-col gap-3">
      {rows.map((c) => (
        <div key={c.key}>
          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: c.color }} aria-hidden />
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
              style={{ width: `${Math.min(100, c.current_pct)}%`, background: c.color }}
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
      ))}
    </div>
  )
}

function HoldingsDriftCard({
  sections,
  tokens,
}: {
  sections: DriftAccountSection[]
  tokens: ReturnType<typeof chartTokens>
}) {
  const [editing, setEditing] = useState<DriftAccountSection | null>(null)
  return (
    <div className="card mt-5 p-5">
      <h2 className="font-semibold">Fördelning inom konton</h2>
      <div className="mt-3 grid gap-6 lg:grid-cols-2">
        {sections.map((s) => (
          <div key={s.id}>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium">
                {s.name} <span className="text-muted">· {formatOre(s.total_ore)}</span>
              </span>
              <button
                onClick={() => setEditing(s)}
                className="text-sm text-accent hover:underline"
              >
                Ändra mål
              </button>
            </div>
            {s.total_ore > 0 ? (
              <DriftView
                rows={s.holdings.map((h, i) => ({
                  key: h.id,
                  label: h.name,
                  color: tokens.series[i % tokens.series.length],
                  current_pct: h.current_pct,
                  target_pct: h.target_pct,
                  drift_pct: h.drift_pct,
                  drift_ore: h.drift_ore,
                }))}
              />
            ) : (
              <p className="text-sm text-muted">Mata in värden på innehaven så visas driften.</p>
            )}
          </div>
        ))}
      </div>
      {editing && <HoldingTargetsDialog section={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

function RebalanceCard({ drift }: { drift: Drift }) {
  const [amountText, setAmountText] = useState('5000')
  const [scope, setScope] = useState<'classes' | number>('classes')
  const contribution = parseKr(amountText) ?? 0
  const { data: plan } = useRebalance(contribution, scope === 'classes' ? undefined : scope)

  return (
    <div className="card mt-5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Rebalanseringsförslag</h2>
        {drift.accounts.length > 0 && (
          <select
            value={String(scope)}
            onChange={(e) => setScope(e.target.value === 'classes' ? 'classes' : Number(e.target.value))}
            className="text-sm"
            aria-label="Rebalansera inom"
          >
            <option value="classes">Hela sparandet (tillgångsslag)</option>
            {drift.accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} (innehav)
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span>Om jag sätter in</span>
        <input
          inputMode="decimal"
          value={amountText}
          onChange={(e) => setAmountText(e.target.value)}
          className="w-28 text-right"
          aria-label="Månadsspar i kronor"
        />
        <span>kr — var gör de mest nytta?</span>
      </div>
      {plan && plan.allocations.length > 0 ? (
        <>
          <ul className="mt-3 flex flex-col gap-1.5 text-sm">
            {plan.allocations.map((a) => (
              <li key={a.asset_class ?? a.id} className="flex justify-between">
                <span>{a.label}</span>
                <span className="tabular font-medium">
                  {plan.requires_selling ? formatSigned(a.amount_ore) : formatOre(a.amount_ore)}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted">
            {plan.requires_selling
              ? 'Utan nysparande krävs omflyttning (positivt = köp, negativt = sälj).'
              : scope === 'classes'
                ? 'Fördelningen fyller underviktade tillgångsslag först, utan att något behöver säljas.'
                : 'Fördelningen fyller underviktade innehav först, utan att något behöver säljas.'}
          </p>
        </>
      ) : (
        <p className="mt-3 text-sm text-muted">
          {contribution > 0
            ? 'Fördelningen ligger redan på målet — spara enligt målprocenten.'
            : 'Ange ett belopp för att få ett fördelningsförslag.'}
        </p>
      )}
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

