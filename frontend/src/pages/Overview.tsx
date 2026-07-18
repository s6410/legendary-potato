import type { ECElementEvent, EChartsOption } from 'echarts'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import {
  useByCategory,
  useCashflow,
  useLinkSuggestions,
  useSummary,
  useTopMerchants,
  useTransactions,
  useTrend,
} from '../api/hooks'
import type { CategoryBucket } from '../api/types'
import { EChart } from '../components/EChart'
import { EmptyState } from '../components/EmptyState'
import { PeriodPicker } from '../components/PeriodPicker'
import { currentMonth, formatMonth, formatOre, formatPct, formatSigned } from '../lib/format'
import { chartTokens, useTheme } from '../lib/theme'

export function OverviewPage() {
  const [month, setMonth] = useState(currentMonth())
  const [drill, setDrill] = useState<CategoryBucket | null>(null)
  const { mode } = useTheme()
  const navigate = useNavigate()

  const { data: anyTxns, isLoading: checkingEmpty } = useTransactions({ page_size: 1 })

  // hoppa till senaste månaden med data om innevarande månad är tom (och
  // användaren inte själv har bläddrat)
  const touched = useRef(false)
  useEffect(() => {
    const latest = anyTxns?.rows[0]?.booked_date.slice(0, 7)
    if (!touched.current && latest && latest < currentMonth()) {
      touched.current = true // hoppa max en gång — ryck inte tillbaka användaren vid refetch
      setMonth(latest)
    }
  }, [anyTxns])
  const { data: summary } = useSummary({ period: month })
  const { data: rootBuckets = [] } = useByCategory({ period: month })
  const { data: drillBuckets = [] } = useByCategory(
    drill ? { period: month, parent_id: drill.category_id } : { period: month },
  )
  const { data: trend = [] } = useTrend({ months: 12 })
  const { data: cashflow = [] } = useCashflow(12)
  const { data: merchants = [] } = useTopMerchants({ period: month, limit: 8 })
  const { data: suggestions = [] } = useLinkSuggestions()

  const tokens = useMemo(() => chartTokens(), [mode]) // eslint-disable-line react-hooks/exhaustive-deps
  const monthRange = useMemo(() => {
    const [y, m] = month.split('-').map(Number)
    const last = new Date(y, m, 0).getDate()
    return { from: `${month}-01`, to: `${month}-${String(last).padStart(2, '0')}` }
  }, [month])

  const uncategorized = useMemo(
    () => rootBuckets.find((b) => b.category_id === null),
    [rootBuckets],
  )

  if (!checkingEmpty && (anyTxns?.total ?? 0) === 0) {
    return (
      <EmptyState
        icon="📒"
        title="Välkommen till Kassaboken!"
        actionLabel="Importera din första fil"
        actionTo="/import"
      >
        Börja med att importera en CSV- eller Excel-export från din bank. Kassaboken lär sig dina
        format och kategorier allteftersom — efter ett par importer sköter det mesta sig självt.
      </EmptyState>
    )
  }

  const expenseBuckets = (drill ? drillBuckets : rootBuckets).filter(
    (b) => b.kind === 'expense' && b.amount_ore < 0,
  )

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Översikt</h1>
        <PeriodPicker
          month={month}
          onChange={(m) => {
            touched.current = true
            setMonth(m)
            setDrill(null)
          }}
        />
      </div>

      {suggestions.length > 0 && (
        <Link
          to="/aterbetalningar"
          className="rounded-lg border border-accent/40 bg-accent/10 px-4 py-2.5 text-sm hover:bg-accent/15"
        >
          ⇄ {suggestions.length} föreslagna återbetalningspar väntar på granskning →
        </Link>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiTile label="Inkomster" value={summary?.current.income_ore} prev={summary?.previous?.income_ore} />
        <KpiTile label="Utgifter" value={summary?.current.expenses_ore} prev={summary?.previous?.expenses_ore} invert />
        <KpiTile label="Netto" value={summary?.current.net_ore} prev={summary?.previous?.net_ore} />
        <div className="card px-4 py-3">
          <div className="text-xs font-medium text-muted">Sparkvot</div>
          <div className="mt-1 text-2xl font-semibold">
            {summary?.current.savings_rate != null ? formatPct(summary.current.savings_rate) : '–'}
          </div>
          {summary?.previous?.savings_rate != null && (
            <div className="mt-0.5 text-xs text-ink-2">
              förra månaden {formatPct(summary.previous.savings_rate)}
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <div className="card p-4">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="font-semibold">
              Utgifter per kategori
              {drill && (
                <>
                  {' '}
                  <span className="text-muted">›</span> {drill.name}
                </>
              )}
            </h2>
            {drill ? (
              <button onClick={() => setDrill(null)} className="text-sm text-accent hover:underline">
                ← Alla kategorier
              </button>
            ) : (
              uncategorized && (
                <Link
                  to={`/transaktioner?uncategorized=1&from=${monthRange.from}&to=${monthRange.to}`}
                  className="rounded-full bg-series-4/15 px-2.5 py-1 text-xs font-medium hover:bg-series-4/25"
                >
                  {uncategorized.transaction_count} okategoriserade
                </Link>
              )
            )}
          </div>
          <p className="mb-2 text-xs text-muted">
            Klicka på en kategori för att borra ner — och vidare till transaktionerna.
          </p>
          <EChart
            height={330}
            option={treemapOption(expenseBuckets, tokens)}
            onEvents={{
              click: (p: ECElementEvent) => {
                const bucket = (p.data as { bucket?: CategoryBucket })?.bucket
                if (!bucket) return
                if (!drill && bucket.category_id !== null) {
                  setDrill(bucket)
                } else {
                  const id = bucket.category_id ?? drill?.category_id
                  navigate(
                    bucket.category_id === null
                      ? `/transaktioner?uncategorized=1&from=${monthRange.from}&to=${monthRange.to}`
                      : `/transaktioner?category_id=${id}&from=${monthRange.from}&to=${monthRange.to}`,
                  )
                }
              },
            }}
          />
        </div>

        <div className="card p-4">
          <h2 className="mb-1 font-semibold">Inkomster & utgifter, 12 månader</h2>
          <p className="mb-2 text-xs text-muted">Klicka på en månad för att se dess transaktioner.</p>
          <EChart
            height={330}
            option={trendOption(trend, tokens)}
            onEvents={{
              click: (p: ECElementEvent) => {
                const m = trend[p.dataIndex ?? -1]?.month
                if (m) {
                  touched.current = true
                  setMonth(m)
                  setDrill(null)
                }
              },
            }}
          />
        </div>

        <div className="card p-4">
          <h2 className="mb-1 font-semibold">Största utgiftsställen i {formatMonth(month, true)}</h2>
          <p className="mb-2 text-xs text-muted">Klicka för att se transaktionerna.</p>
          {merchants.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted">Inga utgifter denna månad.</div>
          ) : (
            <EChart
              height={Math.max(220, merchants.length * 36 + 60)}
              option={merchantsOption(merchants, tokens)}
              onEvents={{
                click: (p: ECElementEvent) => {
                  const m = merchants[p.dataIndex ?? -1]
                  if (m)
                    navigate(
                      `/transaktioner?q=${encodeURIComponent(m.description_norm)}&from=${monthRange.from}&to=${monthRange.to}`,
                    )
                },
              }}
            />
          )}
        </div>

        <div className="card p-4">
          <h2 className="mb-1 font-semibold">Ackumulerat kassaflöde, 12 månader</h2>
          <p className="mb-2 text-xs text-muted">Summan av alla månaders netto över tid.</p>
          <EChart height={Math.max(220, 300)} option={cashflowOption(cashflow, tokens)} />
        </div>
      </div>
    </div>
  )
}

function KpiTile({
  label,
  value,
  prev,
  invert = false,
}: {
  label: string
  value: number | undefined
  prev: number | null | undefined
  invert?: boolean
}) {
  let delta: string | null = null
  let good = false
  if (value != null && prev != null && prev !== 0) {
    const diff = value - prev
    good = invert ? diff > 0 : diff > 0 // för utgifter (negativa) är mindre negativt = bra = diff > 0
    delta = formatSigned(diff)
  }
  return (
    <div className="card px-4 py-3">
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular">{value != null ? formatOre(value) : '–'}</div>
      {delta && (
        <div className={`mt-0.5 text-xs ${good ? 'text-good' : 'text-ink-2'}`}>
          {delta} mot förra månaden
        </div>
      )}
    </div>
  )
}

type Tokens = ReturnType<typeof chartTokens>

function treemapOption(buckets: CategoryBucket[], t: Tokens): EChartsOption {
  const total = buckets.reduce((s, b) => s + Math.abs(b.amount_ore), 0)
  return {
    tooltip: {
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.ink, fontSize: 12 },
      formatter: (p) => {
        const d = (p as unknown as { data?: { bucket?: CategoryBucket } }).data?.bucket
        if (!d) return ''
        const share = total ? Math.round((Math.abs(d.amount_ore) / total) * 100) : 0
        return `<b>${d.name}</b><br/>${formatOre(Math.abs(d.amount_ore))} · ${share} % · ${d.transaction_count} transaktioner`
      },
    },
    series: [
      {
        type: 'treemap',
        roam: false,
        nodeClick: undefined,
        breadcrumb: { show: false },
        itemStyle: { borderColor: t.surface, borderWidth: 2, gapWidth: 2, borderRadius: 4 },
        label: {
          color: '#ffffff',
          fontSize: 12,
          formatter: (p) => {
            const d = (p as unknown as { data?: { bucket?: CategoryBucket } }).data?.bucket
            return d ? `${d.name}\n${formatOre(Math.abs(d.amount_ore))}` : ''
          },
        },
        data: buckets.map((b, i) => ({
          name: b.name,
          value: Math.abs(b.amount_ore),
          bucket: b,
          itemStyle: { color: b.color ?? t.series[i % t.series.length] },
        })),
      },
    ],
  }
}

function trendOption(trend: { month: string; income_ore: number; expenses_ore: number; net_ore: number }[], t: Tokens): EChartsOption {
  return {
    textStyle: { color: t.ink2 },
    legend: {
      data: ['Inkomster', 'Utgifter', 'Netto'],
      textStyle: { color: t.ink2, fontSize: 11 },
      top: 0,
      itemWidth: 14,
      itemHeight: 8,
    },
    grid: { left: 8, right: 8, top: 32, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.ink, fontSize: 12 },
      valueFormatter: (v) => formatOre(Number(v)),
    },
    xAxis: {
      type: 'category',
      data: trend.map((p) => formatMonth(p.month)),
      axisLine: { lineStyle: { color: t.baseline } },
      axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: t.muted, fontSize: 10, formatter: (v: number) => formatOre(v) },
      splitLine: { lineStyle: { color: t.grid } },
    },
    series: [
      {
        name: 'Inkomster',
        type: 'bar',
        data: trend.map((p) => p.income_ore),
        itemStyle: { color: t.series[1], borderRadius: [4, 4, 0, 0] },
        barGap: '10%',
      },
      {
        name: 'Utgifter',
        type: 'bar',
        data: trend.map((p) => Math.abs(p.expenses_ore)),
        itemStyle: { color: t.series[0], borderRadius: [4, 4, 0, 0] },
      },
      {
        name: 'Netto',
        type: 'line',
        data: trend.map((p) => p.net_ore),
        lineStyle: { color: t.ink, width: 2 },
        itemStyle: { color: t.ink },
        symbol: 'circle',
        symbolSize: 6,
      },
    ],
  }
}

function merchantsOption(
  merchants: { merchant: string; amount_ore: number }[],
  t: Tokens,
): EChartsOption {
  const data = [...merchants].reverse()
  return {
    grid: { left: 8, right: 48, top: 8, bottom: 4, containLabel: true },
    tooltip: {
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.ink, fontSize: 12 },
      valueFormatter: (v) => formatOre(Math.abs(Number(v))),
    },
    xAxis: {
      type: 'value',
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'category',
      data: data.map((m) => m.merchant),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: t.ink2, fontSize: 11, width: 150, overflow: 'truncate' },
    },
    series: [
      {
        type: 'bar',
        data: data.map((m) => Math.abs(m.amount_ore)),
        itemStyle: { color: t.series[0], borderRadius: [0, 4, 4, 0] },
        barWidth: 18,
        label: {
          show: true,
          position: 'right',
          color: t.ink2,
          fontSize: 11,
          formatter: (p) => formatOre(Number(p.value)),
        },
      },
    ],
  }
}

function cashflowOption(
  cashflow: { month: string; cumulative_ore?: number }[],
  t: Tokens,
): EChartsOption {
  return {
    grid: { left: 8, right: 8, top: 16, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.ink, fontSize: 12 },
      valueFormatter: (v) => formatOre(Number(v)),
    },
    xAxis: {
      type: 'category',
      data: cashflow.map((p) => formatMonth(p.month)),
      axisLine: { lineStyle: { color: t.baseline } },
      axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: t.muted, fontSize: 10, formatter: (v: number) => formatOre(v) },
      splitLine: { lineStyle: { color: t.grid } },
    },
    series: [
      {
        name: 'Ackumulerat netto',
        type: 'line',
        data: cashflow.map((p) => p.cumulative_ore ?? 0),
        smooth: 0.3,
        lineStyle: { color: t.series[4], width: 2 },
        itemStyle: { color: t.series[4] },
        symbol: 'circle',
        symbolSize: 6,
        areaStyle: { opacity: 0.12, color: t.series[4] },
      },
    ],
  }
}
