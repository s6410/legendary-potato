import { api, useApiMutation, useRecurring } from '../api/hooks'
import { EmptyState } from '../components/EmptyState'
import { formatDate, formatOre } from '../lib/format'

export function SubscriptionsPage() {
  const { data: series = [], isLoading } = useRecurring()
  const override = useApiMutation((body: object) => api.send('POST', '/insights/recurring/override', body))

  const active = series.filter((s) => !s.possibly_ended)
  const ended = series.filter((s) => s.possibly_ended)
  const annualTotal = active.reduce((sum, s) => sum + s.annual_cost_ore, 0)

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-2 text-2xl font-bold">Prenumerationer & återkommande</h1>
      <p className="mb-5 text-sm text-ink-2">
        Automatiskt detekterade återkommande utgifter — abonnemang, räkningar och annat som dras
        regelbundet. Totalt kostar de aktiva ungefär{' '}
        <strong className="text-ink">{formatOre(annualTotal)} per år</strong> (
        {formatOre(Math.round(annualTotal / 12))}/månad).
      </p>

      {!isLoading && series.length === 0 ? (
        <EmptyState icon="↻" title="Inga återkommande utgifter hittade ännu">
          Detekteringen behöver minst tre dragningar med jämn rytm — importera några månaders
          historik så dyker abonnemangen upp här.
        </EmptyState>
      ) : (
        <>
          <SeriesTable
            title={`Aktiva (${active.length})`}
            rows={active}
            onDismiss={(s) =>
              override.mutate({ description_norm: s.description_norm, account_id: s.account_id, status: 'dismissed' })
            }
          />
          {ended.length > 0 && (
            <SeriesTable
              title={`Möjligen avslutade (${ended.length})`}
              rows={ended}
              subdued
              onDismiss={(s) =>
                override.mutate({ description_norm: s.description_norm, account_id: s.account_id, status: 'dismissed' })
              }
            />
          )}
        </>
      )}
    </div>
  )
}

type Series = ReturnType<typeof useRecurring> extends { data?: infer T | undefined }
  ? T extends (infer U)[]
    ? U
    : never
  : never

function SeriesTable({
  title,
  rows,
  subdued = false,
  onDismiss,
}: {
  title: string
  rows: Series[]
  subdued?: boolean
  onDismiss: (s: Series) => void
}) {
  return (
    <div className={`mb-6 ${subdued ? 'opacity-75' : ''}`}>
      <h2 className="mb-3 font-semibold">{title}</h2>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-bord text-left text-xs text-muted">
              <th className="px-4 py-2.5">Beskrivning</th>
              <th className="px-4 py-2.5">Rytm</th>
              <th className="px-4 py-2.5 text-right">Belopp</th>
              <th className="px-4 py-2.5 text-right">Per år</th>
              <th className="px-4 py-2.5">Nästa dragning</th>
              <th className="px-4 py-2.5">Kategori</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={`${s.description_norm}-${s.account_id}`} className="border-b border-bord/50 last:border-0">
                <td className="max-w-xs truncate px-4 py-2 font-medium">{s.display_name}</td>
                <td className="whitespace-nowrap px-4 py-2 text-xs text-ink-2">
                  {s.cadence_label}
                  {s.variable_amount && ' · varierande'}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right tabular">
                  {formatOre(s.median_amount_ore)}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right tabular font-medium">
                  {formatOre(s.annual_cost_ore)}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-ink-2">
                  {s.possibly_ended ? '—' : formatDate(s.next_expected_date)}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-xs text-ink-2">
                  {s.category_path ?? 'Okategoriserad'}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right">
                  <button
                    onClick={() => onDismiss(s)}
                    className="text-xs text-muted hover:text-bad hover:underline"
                    title="Dölj denna serie permanent"
                  >
                    dölj
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
