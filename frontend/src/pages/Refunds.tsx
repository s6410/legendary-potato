import { api, useApiMutation, useConfirmedLinks, useLinkSuggestions } from '../api/hooks'
import type { LinkSuggestion } from '../api/types'
import { AmountText } from '../components/AmountText'
import { EmptyState } from '../components/EmptyState'
import { formatDate } from '../lib/format'

export function RefundsPage() {
  const { data: suggestions = [], isLoading } = useLinkSuggestions()
  const { data: confirmed = [] } = useConfirmedLinks()

  const scan = useApiMutation(() => api.send<{ created: number }>('POST', '/links/scan'))
  const act = useApiMutation(({ id, action }: { id: number; action: 'confirm' | 'dismiss' }) =>
    api.send('POST', `/links/${id}/${action}`),
  )
  const unlink = useApiMutation((id: number) => api.send('DELETE', `/links/${id}`))

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Återbetalningar & kvittningar</h1>
        <button
          onClick={() => scan.mutate(undefined)}
          disabled={scan.isPending}
          className="rounded-lg border border-baseline px-3 py-1.5 text-sm hover:bg-grid disabled:opacity-50"
        >
          Sök efter nya par
        </button>
      </div>

      <p className="mb-5 text-sm text-ink-2">
        Kassaboken letar efter par med motsatta belopp hos samma handlare (återbetalningar) och
        mellan dina konton (överföringar). Bekräftade par räknas bort ur all statistik så att en
        återköpt vara inte ser ut som både utgift och inkomst.
      </p>

      <h2 className="mb-3 font-semibold">Förslag ({suggestions.length})</h2>
      {!isLoading && suggestions.length === 0 ? (
        <div className="card px-5 py-8 text-center text-sm text-muted">
          Inga obekräftade förslag just nu — nya dyker upp automatiskt efter import.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {suggestions.map((s) => (
            <LinkCard key={s.id} link={s}>
              <button
                onClick={() => act.mutate({ id: s.id, action: 'confirm' })}
                className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
              >
                Bekräfta
              </button>
              <button
                onClick={() => act.mutate({ id: s.id, action: 'dismiss' })}
                className="rounded-lg border border-baseline px-3 py-1.5 text-sm hover:bg-grid"
              >
                Avfärda
              </button>
            </LinkCard>
          ))}
        </div>
      )}

      {confirmed.length > 0 && (
        <>
          <h2 className="mb-3 mt-8 font-semibold">Bekräftade par ({confirmed.length})</h2>
          <div className="flex flex-col gap-3">
            {confirmed.map((s) => (
              <LinkCard key={s.id} link={s} subdued>
                <button
                  onClick={() => unlink.mutate(s.id)}
                  className="text-sm text-bad hover:underline"
                >
                  Ta bort länken
                </button>
              </LinkCard>
            ))}
          </div>
        </>
      )}

      {!isLoading && suggestions.length === 0 && confirmed.length === 0 && (
        <div className="mt-8">
          <EmptyState icon="⇄" title="Inget att kvitta ännu">
            När en återbetalning dyker upp i en import föreslås paret här automatiskt.
          </EmptyState>
        </div>
      )}
    </div>
  )
}

function LinkCard({
  link,
  children,
  subdued = false,
}: {
  link: LinkSuggestion
  children: React.ReactNode
  subdued?: boolean
}) {
  return (
    <div className={`card flex flex-wrap items-center gap-4 p-4 ${subdued ? 'opacity-80' : ''}`}>
      <span
        className="rounded-full bg-grid px-2.5 py-1 text-xs font-medium text-ink-2"
        title={link.score != null ? `säkerhet ${Math.round(link.score * 100)} %` : undefined}
      >
        {link.kind === 'refund' ? '⇄ Återbetalning' : '⇅ Överföring'}
      </span>
      <div className="min-w-0 flex-1">
        {[link.txn_a, link.txn_b].map((t) => (
          <div key={t.id} className="flex items-center justify-between gap-3 text-sm">
            <span className="truncate">
              <span className="text-muted">{formatDate(t.booked_date)}</span> {t.description}
              <span className="ml-1 text-xs text-muted">({t.account_name})</span>
            </span>
            <AmountText ore={t.amount_ore} className="shrink-0" />
          </div>
        ))}
      </div>
      <div className="flex gap-2">{children}</div>
    </div>
  )
}
