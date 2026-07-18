import type { EChartsOption } from 'echarts'
import { useMemo } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { useYearlyReport } from '../api/hooks'
import { AmountText } from '../components/AmountText'
import { EChart } from '../components/EChart'
import { formatMonth, formatOre, formatPct } from '../lib/format'
import { chartTokens, useTheme } from '../lib/theme'

export function YearlyReportPage() {
  const params = useParams()
  const navigate = useNavigate()
  const year = Number(params.year ?? new Date().getFullYear())
  const { data: report, isLoading } = useYearlyReport(year)
  const { mode } = useTheme()
  const tokens = useMemo(() => chartTokens(), [mode]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <h1 className="text-2xl font-bold">Ditt ekonomiska år</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate(`/rapport/ar/${year - 1}`)}
            className="rounded-lg border border-baseline px-2.5 py-1.5 text-sm hover:bg-grid"
          >
            ← {year - 1}
          </button>
          <span className="px-2 text-lg font-semibold">{year}</span>
          <button
            onClick={() => navigate(`/rapport/ar/${year + 1}`)}
            disabled={year >= new Date().getFullYear()}
            className="rounded-lg border border-baseline px-2.5 py-1.5 text-sm hover:bg-grid disabled:opacity-40"
          >
            {year + 1} →
          </button>
          <button
            onClick={() => window.print()}
            className="ml-2 rounded-lg border border-baseline px-3 py-1.5 text-sm hover:bg-grid"
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
            <h2 className="text-lg font-semibold">{year} i siffror</h2>
            <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="Inkomster" value={formatOre(report.summary.income_ore)} />
              <Stat label="Utgifter" value={formatOre(report.summary.expenses_ore)} />
              <Stat label="Netto" value={formatOre(report.summary.net_ore)} />
              <Stat
                label="Snittsparkvot"
                value={report.avg_savings_rate != null ? formatPct(report.avg_savings_rate) : '–'}
              />
            </div>
            {report.previous_summary.transaction_count > 0 && (
              <p className="mt-3 text-sm text-ink-2">
                Jämfört med {year - 1}: utgifterna{' '}
                {diffWord(report.summary.expenses_ore, report.previous_summary.expenses_ore)},
                nettot {diffWord(report.summary.net_ore, report.previous_summary.net_ore, true)}.
              </p>
            )}
          </div>

          <div className="card p-4">
            <h2 className="mb-2 font-semibold">Månad för månad</h2>
            <EChart height={260} option={monthsOption(report.months, tokens)} />
          </div>

          {report.category_changes.length > 0 && (
            <div className="card p-5">
              <h2 className="mb-1 font-semibold">Största förändringarna mot {year - 1}</h2>
              <ul className="mt-2 flex flex-col gap-1.5 text-sm">
                {report.category_changes.map((c) => (
                  <li key={`${c.category_id}`} className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ background: c.color ?? 'var(--muted)' }}
                        aria-hidden
                      />
                      {c.name}
                    </span>
                    <span className="tabular text-ink-2">
                      {formatOre(c.current_ore)}{' '}
                      <span className={c.diff_ore > 0 ? 'text-bad' : 'text-good'}>
                        ({c.diff_ore > 0 ? '+' : '−'}
                        {formatOre(Math.abs(c.diff_ore))})
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid gap-5 sm:grid-cols-2">
            {report.biggest_month && (
              <div className="card p-5">
                <h2 className="font-semibold">Dyraste månaden</h2>
                <p className="mt-2 text-2xl font-bold capitalize">
                  {formatMonth(report.biggest_month.month, true)}
                </p>
                <p className="mt-1 text-sm text-ink-2">
                  {formatOre(Math.abs(report.biggest_month.expenses_ore))} i utgifter
                  {report.biggest_month_top_category && (
                    <>
                      {' '}
                      — störst var {report.biggest_month_top_category.name} med{' '}
                      {formatOre(Math.abs(report.biggest_month_top_category.amount_ore))}
                    </>
                  )}
                  .{' '}
                  <Link to={`/rapport/${report.biggest_month.month}`} className="text-accent hover:underline">
                    Se månadsrapporten →
                  </Link>
                </p>
              </div>
            )}

            <div className="card p-5">
              <h2 className="font-semibold">Sparandet</h2>
              {report.savings_start_ore != null && report.savings_end_ore != null ? (
                <>
                  <p className="mt-2 text-2xl font-bold tabular">
                    <AmountText ore={report.savings_end_ore - report.savings_start_ore} />
                  </p>
                  <p className="mt-1 text-sm text-ink-2">
                    Från {formatOre(report.savings_start_ore)} till {formatOre(report.savings_end_ore)} under året.
                  </p>
                </>
              ) : (
                <p className="mt-2 text-sm text-muted">
                  Inga sparande-värden registrerade för året.
                </p>
              )}
            </div>
          </div>

          <div className="card p-5">
            <h2 className="font-semibold">Prenumerationsfacit</h2>
            <p className="mt-1 text-sm text-ink-2">
              {report.subscriptions_active.length} aktiva återkommande kostnader ≈{' '}
              <strong className="text-ink">{formatOre(report.subscriptions_annual_cost_ore)}/år</strong>
              {report.subscriptions_cancelled.length > 0 && (
                <>
                  . Under året upphörde {report.subscriptions_cancelled.length} — värda{' '}
                  <strong className="text-good">
                    {formatOre(report.subscriptions_cancelled_savings_ore)}/år
                  </strong>{' '}
                  ({report.subscriptions_cancelled.map((s) => s.display_name).join(', ')})
                </>
              )}
              .
            </p>
          </div>

          <div className="card p-5">
            <h2 className="mb-2 font-semibold">Årets största utgiftsställen</h2>
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

function diffWord(current: number, previous: number, higherIsGood = false): string {
  const diff = Math.abs(current) - Math.abs(previous)
  const word = diff > 0 ? 'ökade' : 'minskade'
  void higherIsGood
  return `${word} med ${formatOre(Math.abs(diff))}`
}

function monthsOption(
  months: { month: string; income_ore: number; expenses_ore: number; net_ore: number }[],
  t: ReturnType<typeof chartTokens>,
): EChartsOption {
  return {
    legend: { data: ['Inkomster', 'Utgifter'], textStyle: { color: t.ink2, fontSize: 11 }, top: 0 },
    grid: { left: 8, right: 8, top: 30, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.ink, fontSize: 12 },
      valueFormatter: (v) => formatOre(Number(v)),
    },
    xAxis: {
      type: 'category',
      data: months.map((m) => formatMonth(m.month)),
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
        data: months.map((m) => m.income_ore),
        itemStyle: { color: t.series[1], borderRadius: [4, 4, 0, 0] },
      },
      {
        name: 'Utgifter',
        type: 'bar',
        data: months.map((m) => Math.abs(m.expenses_ore)),
        itemStyle: { color: t.series[0], borderRadius: [4, 4, 0, 0] },
      },
    ],
  }
}
