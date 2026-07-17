import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { api, useAccounts, useApiMutation } from '../api/hooks'
import type { ImportProfile } from '../api/types'
import { Modal } from '../components/Modal'
import { setTheme, useTheme } from '../lib/theme'

export function SettingsPage() {
  const { pref } = useTheme()
  const { data: accounts = [] } = useAccounts()
  const { data: profiles = [] } = useQuery({
    queryKey: ['profiles'],
    queryFn: () => api.get<ImportProfile[]>('/import/profiles'),
  })
  const [renamingAccount, setRenamingAccount] = useState<{ id: number; name: string } | null>(null)

  const patchAccount = useApiMutation(({ id, body }: { id: number; body: object }) =>
    api.send('PATCH', `/accounts/${id}`, body),
  )
  const deleteAccount = useApiMutation((id: number) => api.send('DELETE', `/accounts/${id}`))
  const deleteProfile = useApiMutation((id: number) => api.send('DELETE', `/import/profiles/${id}`))

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <h1 className="text-2xl font-bold">Inställningar</h1>

      <section className="card p-5">
        <h2 className="font-semibold">Utseende</h2>
        <div className="mt-3 flex gap-2">
          {(
            [
              ['light', '☀ Ljust'],
              ['dark', '☾ Mörkt'],
              ['system', '⚙ Följ systemet'],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setTheme(value)}
              className={`rounded-lg border px-3 py-1.5 text-sm ${
                pref === value
                  ? 'border-accent bg-accent/10 font-medium text-accent'
                  : 'border-baseline hover:bg-grid'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="font-semibold">Konton</h2>
        <p className="mt-1 text-xs text-muted">
          Transaktionskonton skapas vid import. Konton med transaktioner kan inaktiveras men inte
          tas bort.
        </p>
        <table className="mt-3 w-full text-sm">
          <tbody>
            {accounts.map((a) => (
              <tr key={a.id} className="border-b border-bord/50 last:border-0">
                <td className={`py-2 ${a.is_active ? '' : 'opacity-50'}`}>
                  <span className="font-medium">{a.name}</span>
                  <span className="ml-2 text-xs text-muted">{a.transaction_count} transaktioner</span>
                </td>
                <td className="py-2 text-right text-xs">
                  <button
                    onClick={() => setRenamingAccount({ id: a.id, name: a.name })}
                    className="text-accent hover:underline"
                  >
                    byt namn
                  </button>
                  {a.transaction_count === 0 ? (
                    <button
                      onClick={() => deleteAccount.mutate(a.id)}
                      className="ml-3 text-bad hover:underline"
                    >
                      ta bort
                    </button>
                  ) : (
                    <button
                      onClick={() => patchAccount.mutate({ id: a.id, body: { is_active: !a.is_active } })}
                      className="ml-3 text-ink-2 hover:underline"
                    >
                      {a.is_active ? 'inaktivera' : 'aktivera'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {accounts.length === 0 && (
              <tr>
                <td className="py-4 text-center text-muted">Inga konton ännu.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="card p-5">
        <h2 className="font-semibold">Importprofiler</h2>
        <p className="mt-1 text-xs text-muted">
          Sparade filformat — en per bankexportlayout. Ta bort en profil för att köra
          mappningsguiden på nytt vid nästa import.
        </p>
        <table className="mt-3 w-full text-sm">
          <tbody>
            {profiles.map((p) => (
              <tr key={p.id} className="border-b border-bord/50 last:border-0">
                <td className="py-2">
                  <span className="font-medium">{p.name}</span>
                  <span className="ml-2 text-xs text-muted">
                    {p.file_type.toUpperCase()}
                    {p.invert_sign && ' · omvänt tecken'}
                  </span>
                </td>
                <td className="py-2 text-right text-xs">
                  <button
                    onClick={() => deleteProfile.mutate(p.id)}
                    className="text-bad hover:underline"
                  >
                    ta bort
                  </button>
                </td>
              </tr>
            ))}
            {profiles.length === 0 && (
              <tr>
                <td className="py-4 text-center text-muted">
                  Inga profiler ännu — de skapas vid första importen av varje format.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {deleteProfile.isError && (
          <p className="mt-2 text-xs text-bad">{(deleteProfile.error as Error).message}</p>
        )}
      </section>

      <section className="card p-5">
        <h2 className="font-semibold">Om Kassaboken</h2>
        <p className="mt-2 text-sm text-ink-2">
          All data lagras lokalt på din dator i en SQLite-databas — ingenting lämnar din maskin.
          Öppen källkod, byggd för att ersätta trötta Excelark.
        </p>
      </section>

      {renamingAccount && (
        <Modal title="Byt namn på konto" onClose={() => setRenamingAccount(null)}>
          <div className="flex flex-col gap-3 text-sm">
            <input
              value={renamingAccount.name}
              onChange={(e) => setRenamingAccount({ ...renamingAccount, name: e.target.value })}
              autoFocus
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setRenamingAccount(null)}
                className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid"
              >
                Avbryt
              </button>
              <button
                onClick={() => {
                  patchAccount.mutate({
                    id: renamingAccount.id,
                    body: { name: renamingAccount.name.trim() },
                  })
                  setRenamingAccount(null)
                }}
                disabled={!renamingAccount.name.trim()}
                className="rounded-lg bg-accent px-4 py-2 font-medium text-white hover:opacity-90 disabled:opacity-50"
              >
                Spara
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
