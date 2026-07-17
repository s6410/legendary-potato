import { Link } from 'react-router-dom'

import { api, useApiMutation, useBatches } from '../api/hooks'
import { EmptyState } from '../components/EmptyState'

export function ImportHistoryPage() {
  const { data: batches = [], isLoading } = useBatches()
  const revert = useApiMutation((id: number) => api.send('POST', `/import/batches/${id}/revert`))

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Importhistorik</h1>
        <Link to="/import" className="text-sm text-accent hover:underline">
          ← Tillbaka till import
        </Link>
      </div>

      {!isLoading && batches.length === 0 ? (
        <EmptyState icon="🗂" title="Inga importer ännu" actionLabel="Importera" actionTo="/import" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-bord text-left text-xs text-muted">
                <th className="px-4 py-2.5">Datum</th>
                <th className="px-4 py-2.5">Fil</th>
                <th className="px-4 py-2.5">Konto</th>
                <th className="px-4 py-2.5">Profil</th>
                <th className="px-4 py-2.5 text-right">Nya</th>
                <th className="px-4 py-2.5 text-right">Dubbletter</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => (
                <tr
                  key={b.id}
                  className={`border-b border-bord/50 last:border-0 ${b.status === 'reverted' ? 'opacity-50' : ''}`}
                >
                  <td className="whitespace-nowrap px-4 py-2 text-ink-2">{b.imported_at.slice(0, 16)}</td>
                  <td className="max-w-xs truncate px-4 py-2">{b.filename}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-ink-2">{b.account_name}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-ink-2">{b.profile_name}</td>
                  <td className="px-4 py-2 text-right tabular">{b.inserted_count}</td>
                  <td className="px-4 py-2 text-right tabular text-muted">{b.duplicate_count}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-right text-xs">
                    {b.status === 'reverted' ? (
                      <span className="text-muted">ångrad</span>
                    ) : (
                      <button
                        onClick={() => {
                          if (confirm(`Ångra importen av ${b.filename}? ${b.inserted_count} transaktioner tas bort.`))
                            revert.mutate(b.id)
                        }}
                        className="text-bad hover:underline"
                      >
                        ångra
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
