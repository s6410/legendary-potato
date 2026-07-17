import * as echarts from 'echarts'
import { useEffect, useRef } from 'react'

import { useTheme } from '../lib/theme'

interface Props {
  option: echarts.EChartsOption
  height?: number | string
  onEvents?: Record<string, (params: echarts.ECElementEvent) => void>
  className?: string
}

/** Tunn temamedveten wrapper runt ECharts med resize-hantering. */
export function EChart({ option, height = 320, onEvents, className }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const { mode } = useTheme()

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chartRef.current = chart
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(ref.current)
    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.setOption(option, { notMerge: true })
  }, [option, mode])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !onEvents) return
    for (const [event, handler] of Object.entries(onEvents)) {
      chart.on(event, handler as never)
    }
    return () => {
      for (const event of Object.keys(onEvents)) chart.off(event)
    }
  }, [onEvents])

  return <div ref={ref} className={className} style={{ height, width: '100%' }} />
}

/** Gemensam grundstil för alla diagram: recessiva axlar/grid, systemtypsnitt. */
export function baseChartStyle(tokens: ReturnType<typeof import('../lib/theme').chartTokens>) {
  return {
    textStyle: { fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: tokens.ink2 },
    tooltip: {
      backgroundColor: tokens.surface,
      borderColor: tokens.grid,
      textStyle: { color: tokens.ink, fontSize: 12 },
      extraCssText: 'box-shadow: 0 4px 16px rgba(0,0,0,0.12); border-radius: 8px;',
    },
    axisCommon: {
      axisLine: { lineStyle: { color: tokens.baseline } },
      axisTick: { show: false },
      axisLabel: { color: tokens.muted, fontSize: 11 },
      splitLine: { lineStyle: { color: tokens.grid, width: 1 } },
    },
  }
}
