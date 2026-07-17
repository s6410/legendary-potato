import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api, useApiMutation, useCategories } from '../api/hooks'
import type { Category } from '../api/types'
import { Modal } from '../components/Modal'

const KIND_LABELS: Record<string, string> = {
  expense: 'Utgift',
  income: 'Inkomst',
  transfer: 'Överföring',
  exclude: 'Exkluderas',
}

export function CategoriesPage() {
  const { data: tree = [] } = useCategories()
  const [adding, setAdding] = useState<{ parent: Category | null } | null>(null)
  const [renaming, setRenaming] = useState<Category | null>(null)
  const [deleting, setDeleting] = useState<Category | null>(null)

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Kategorier</h1>
        <button
          onClick={() => setAdding({ parent: null })}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
        >
          + Ny huvudkategori
        </button>
      </div>

      <div className="flex flex-col gap-3">
        {tree.map((root) => (
          <div key={root.id} className="card p-4">
            <div className="flex items-center gap-2">
              <span
                className="h-3 w-3 rounded-full"
                style={{ background: root.color ?? 'var(--muted)' }}
                aria-hidden
              />
              <span className="font-semibold">{root.name}</span>
              <span className="rounded-full bg-grid px-2 py-0.5 text-xs text-ink-2">
                {KIND_LABELS[root.kind] ?? root.kind}
              </span>
              <span className="ml-auto flex gap-2 text-xs">
                <button onClick={() => setAdding({ parent: root })} className="text-accent hover:underline">
                  + underkategori
                </button>
                <button onClick={() => setRenaming(root)} className="text-ink-2 hover:underline">
                  byt namn
                </button>
                <button onClick={() => setDeleting(root)} className="text-bad hover:underline">
                  ta bort
                </button>
              </span>
            </div>
            {root.children.length > 0 && (
              <ul className="mt-2 flex flex-col">
                {root.children.map((child) => (
                  <li
                    key={child.id}
                    className="flex items-center gap-2 border-t border-bord/50 py-1.5 pl-5 text-sm"
                  >
                    <span>{child.name}</span>
                    {child.transaction_count > 0 && (
                      <Link
                        to={`/transaktioner?category_id=${child.id}`}
                        className="text-xs text-muted hover:text-accent"
                      >
                        {child.transaction_count} transaktioner
                      </Link>
                    )}
                    {child.rule_count > 0 && (
                      <span className="text-xs text-muted">· {child.rule_count} regler</span>
                    )}
                    <span className="ml-auto flex gap-2 text-xs">
                      <button onClick={() => setRenaming(child)} className="text-ink-2 hover:underline">
                        byt namn
                      </button>
                      <button onClick={() => setDeleting(child)} className="text-bad hover:underline">
                        ta bort
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>

      {adding && <AddDialog parent={adding.parent} onClose={() => setAdding(null)} />}
      {renaming && <RenameDialog category={renaming} onClose={() => setRenaming(null)} />}
      {deleting && <DeleteDialog category={deleting} onClose={() => setDeleting(null)} />}
    </div>
  )
}

function AddDialog({ parent, onClose }: { parent: Category | null; onClose: () => void }) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState('expense')
  const mutation = useApiMutation(
    () =>
      api.send('POST', '/categories', {
        name: name.trim(),
        parent_id: parent?.id ?? null,
        kind: parent ? undefined : kind,
      }),
    onClose,
  )
  return (
    <Modal title={parent ? `Ny underkategori i ${parent.name}` : 'Ny huvudkategori'} onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="font-medium">Namn</span>
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </label>
        {!parent && (
          <label className="flex flex-col gap-1">
            <span className="font-medium">Typ</span>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(KIND_LABELS).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}
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

function RenameDialog({ category, onClose }: { category: Category; onClose: () => void }) {
  const [name, setName] = useState(category.name)
  const mutation = useApiMutation(
    () => api.send('PATCH', `/categories/${category.id}`, { name: name.trim() }),
    onClose,
  )
  return (
    <Modal title="Byt namn" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={!name.trim() || mutation.isPending}
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

function DeleteDialog({ category, onClose }: { category: Category; onClose: () => void }) {
  const { data: tree = [] } = useCategories()
  const inUse =
    category.transaction_count > 0 ||
    category.children.some((c) => c.transaction_count > 0)
  const [reassignTo, setReassignTo] = useState<number | ''>('')

  const options = tree
    .flatMap((r) => [r, ...r.children])
    .filter((c) => c.id !== category.id && !category.children.some((ch) => ch.id === c.id))

  const mutation = useApiMutation(
    () =>
      api.send(
        'DELETE',
        `/categories/${category.id}${inUse && reassignTo ? `?reassign_to=${reassignTo}` : ''}`,
      ),
    onClose,
  )
  return (
    <Modal title={`Ta bort ${category.name}?`} onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        {inUse ? (
          <>
            <p className="text-ink-2">
              Kategorin används av transaktioner. Välj vart de ska flyttas:
            </p>
            <select
              value={reassignTo}
              onChange={(e) => setReassignTo(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">Välj kategori …</option>
              {options.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </>
        ) : (
          <p className="text-ink-2">Kategorin och dess regler tas bort permanent.</p>
        )}
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={mutation.isPending || (inUse && !reassignTo)}
            onClick={() => mutation.mutate(undefined)}
            className="rounded-lg bg-bad px-4 py-2 font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Ta bort
          </button>
        </div>
      </div>
    </Modal>
  )
}
