import type { EChartsOption } from 'echarts'
import { useState } from 'react'

import { api, useApiMutation, useSettings } from '../../api/hooks'
import type { SavingsPlanSummary } from '../../api/types'
import { formatMonth, formatOre, parseKr } from '../../lib/format'
import type { chartTokens } from '../../lib/theme'
import { EChart } from '../EChart'

const DEFAULT_RATES = [4, 7, 10]
const MAX_RATE = 30

export interface ForecastSettings {
  rates: number[]
  rateTexts: string[]
  setRateText: (index: number, value: string) => void
  goalText: string
  setGoalText: (value: string) => void
  goalOre: number | null
  persist: () => void
}

function parseRate(text: string): number | null {
  const value = parseFloat(text.replace(',', '.'))
  return Number.isFinite(value) && value >= 0 && value <= MAX_RATE ? value : null
}

/** Procentsatser och målbelopp: läses från inställningarna, sparas vid ändring. */
export function useForecastSettings(): ForecastSettings {
  const { data: settings } = useSettings()
  const [rateDrafts, setRateDrafts] = useState<string[] | null>(null)
  const [goalDraft, setGoalDraft] = useState<string | null>(null)

  const stored = (settings?.savings_forecast_rates ?? '')
    .split(',')
    .map(parseRate)
    .filter((v): v is number => v != null)
  const storedRates = stored.length > 0 ? stored.slice(0, 3) : DEFAULT_RATES
  const rateTexts = rateDrafts ?? storedRates.map((r) => String(r).replace('.', ','))
  const rates = rateTexts.map(parseRate).filter((v): v is number => v != null)

  const storedGoalOre = settings?.savings_goal_ore ? Number(settings.savings_goal_ore) : null
  const goalText = goalDraft ?? (storedGoalOre != null ? String(storedGoalOre / 100) : '')
  const goalOre = parseKr(goalText)

  const save = useApiMutation((body: Record<string, string | null>) =>
    api.send('PUT', '/settings', body),
  )
  const persist = () => {
    if (rates.length === 0) return
    save.mutate({
      savings_forecast_rates: rates.join(','),
      savings_goal_ore: goalOre != null && goalOre > 0 ? String(goalOre) : null,
    })
  }

  return {
    rates,
    rateTexts,
    setRateText: (index, value) => {
      const next = [...rateTexts]
      next[index] = value
      setRateDrafts(next)
    },
    goalText,
    setGoalText: setGoalDraft,
    goalOre,
    persist,
  }
}

interface ForecastCardProps {
  state: ForecastSettings
  summary: SavingsPlanSummary
  tokens: ReturnType<typeof chartTokens>
}

export function ForecastCard({ state, summary, tokens }: ForecastCardProps) {
  const emphasized = Math.floor(summary.forecast.length / 2)
  return (
    <div className="card mt-5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">Prognos</h2>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-ink-2">Årlig avkastning</span>
          {state.rateTexts.map((text, i) => (
            <span key={i} className="flex items-center gap-1">
              <input
                inputMode="decimal"
                className="w-14 text-right"
                value={text}
                onChange={(e) => state.setRateText(i, e.target.value)}
                onBlur={state.persist}
                aria-label={`Scenario ${i + 1} (%)`}
              />
              %
            </span>
          ))}
          <span className="ml-3 text-ink-2">Målbelopp</span>
          <input
            inputMode="decimal"
            className="w-28 text-right"
            placeholder="valfritt"
            value={state.goalText}
            onChange={(e) => state.setGoalText(e.target.value)}
            onBlur={state.persist}
            aria-label="Eget målbelopp (kr)"
          />
          <span>kr</span>
        </div>
      </div>

      {summary.forecast.length > 0 && (
        <EChart height={280} option={forecastOption(summary, tokens, emphasized)} />
      )}

      {summary.milestones.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1 text-sm">
          {summary.milestones.map((m) => {
            const mid = m.reached[emphasized] ?? m.reached[0]
            return (
              <li key={m.amount_ore} className="flex justify-between">
                <span className={m.is_goal ? 'font-medium' : 'text-ink-2'}>
                  {m.is_goal ? 'Ditt mål: ' : ''}
                  {formatOre(m.amount_ore)}
                </span>
                <span className="tabular text-ink-2">
                  {mid.date
                    ? `nås ca ${formatMonth(mid.date.slice(0, 7))} vid ${String(mid.rate_pct).replace('.', ',')} %`
                    : `nås inte inom 30 år vid ${String(mid.rate_pct).replace('.', ',')} %`}
                </span>
              </li>
            )
          })}
        </ul>
      )}
      <p className="mt-2 text-xs text-muted">
        Antar månadssparande enligt planen och jämn avkastning — verkligheten svänger mer.
      </p>
    </div>
  )
}

function forecastOption(
  summary: SavingsPlanSummary,
  t: ReturnType<typeof chartTokens>,
  emphasized: number,
): EChartsOption {
  const startYear = new Date().getFullYear()
  const years = summary.forecast[0].points.map((p) => String(startYear + p.year))
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
      data: years,
      axisLine: { lineStyle: { color: t.baseline } },
      axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: t.muted, fontSize: 10, formatter: (v: number) => formatOre(v) },
      splitLine: { lineStyle: { color: t.grid } },
    },
    series: summary.forecast.map((f, i) => ({
      name: `${String(f.rate_pct).replace('.', ',')} %`,
      type: 'line',
      data: f.points.map((p) => p.value_ore),
      symbol: 'none',
      lineStyle: { width: i === emphasized ? 3 : 1.5 },
      itemStyle: { color: t.series[i % t.series.length] },
      color: t.series[i % t.series.length],
    })),
  }
}
