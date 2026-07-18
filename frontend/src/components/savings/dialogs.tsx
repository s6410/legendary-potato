import { useState } from 'react'

import { api, useApiMutation, useTargets } from '../../api/hooks'
import type { DriftAccountSection, SavingsAccount } from '../../api/types'
import { parseKr } from '../../lib/format'
import { Modal } from '../Modal'

export const CLASS_OPTIONS = [
  ['equity', 'Aktier'],
  ['fixed_income', 'Räntor'],
  ['cash', 'Kontanter'],
  ['other', 'Övrigt'],
] as const

export function SnapshotDialog({ accounts, onClose }: { accounts: SavingsAccount[]; onClose: () => void }) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  // värden anges bara på lövnivå: innehav och konton utan innehav, i kontoordning
  const leaves = accounts
    .filter((a) => a.parent_id == null)
    .flatMap((a) => (a.has_holdings ? accounts.filter((h) => h.parent_id === a.id) : [a]))
  const parentName = (a: SavingsAccount) =>
    a.parent_id != null ? accounts.find((p) => p.id === a.parent_id)?.name : null
  const [values, setValues] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      leaves.map((a) => [a.id, a.latest_value_ore != null ? String(a.latest_value_ore / 100) : '']),
    ),
  )
  const mutation = useApiMutation(
    () =>
      api.send('POST', '/savings/snapshots', {
        snapshot_date: date,
        values: leaves
          .filter((a) => parseKr(values[a.id] ?? '') != null)
          .map((a) => ({
            savings_account_id: a.id,
            value_ore: parseKr(values[a.id])!,
          })),
      }),
    onClose,
  )
  return (
    <Modal title="Uppdatera värden" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="font-medium">Datum</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        {leaves.map((a) => (
          <label key={a.id} className="flex items-center justify-between gap-3">
            <span>
              {parentName(a) && <span className="text-xs text-muted">{parentName(a)} · </span>}
              {a.name} <span className="text-xs text-muted">({a.asset_class_label})</span>
            </span>
            <input
              inputMode="decimal"
              className="w-36 text-right"
              placeholder="kr"
              value={values[a.id] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [a.id]: e.target.value }))}
            />
          </label>
        ))}
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={mutation.isPending}
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

export function AddAccountDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [assetClass, setAssetClass] = useState('equity')
  const mutation = useApiMutation(
    () => api.send('POST', '/savings/accounts', { name: name.trim(), asset_class: assetClass }),
    onClose,
  )
  return (
    <Modal title="Nytt sparkonto" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="font-medium">Namn</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="t.ex. ISK Avanza" autoFocus />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium">Tillgångsslag</span>
          <select value={assetClass} onChange={(e) => setAssetClass(e.target.value)}>
            {CLASS_OPTIONS.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
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

export function AddHoldingDialog({ parent, onClose }: { parent: SavingsAccount; onClose: () => void }) {
  const [name, setName] = useState('')
  const [assetClass, setAssetClass] = useState('equity')
  const [targetText, setTargetText] = useState('')
  const mutation = useApiMutation(
    () =>
      api.send('POST', '/savings/accounts', {
        name: name.trim(),
        asset_class: assetClass,
        parent_id: parent.id,
        target_pct: targetText.trim() ? parseFloat(targetText.replace(',', '.')) : null,
      }),
    onClose,
  )
  return (
    <Modal title={`Nytt innehav i ${parent.name}`} onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="font-medium">Namn</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="t.ex. LF Global Indexnära"
            autoFocus
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium">Tillgångsslag</span>
          <select value={assetClass} onChange={(e) => setAssetClass(e.target.value)}>
            {CLASS_OPTIONS.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium">Målandel inom kontot (%)</span>
          <input
            inputMode="decimal"
            value={targetText}
            onChange={(e) => setTargetText(e.target.value)}
            placeholder="t.ex. 82"
          />
          <span className="text-xs text-muted">
            Kan lämnas tomt och sättas senare via "Ändra mål". Alla innehavs mål ska summera
            till 100 %.
          </span>
        </label>
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

export function TargetsDialog({ onClose }: { onClose: () => void }) {
  const { data: targets = [] } = useTargets()
  const [values, setValues] = useState<Record<string, string> | null>(null)
  const current =
    values ??
    Object.fromEntries(
      CLASS_OPTIONS.map(([k]) => [k, String(targets.find((t) => t.asset_class === k)?.target_pct ?? 0)]),
    )
  const total = Object.values(current).reduce((s, v) => s + (parseFloat(v.replace(',', '.')) || 0), 0)

  const mutation = useApiMutation(
    () =>
      api.send('PUT', '/savings/targets', {
        targets: Object.entries(current)
          .filter(([, v]) => (parseFloat(v.replace(',', '.')) || 0) > 0)
          .map(([asset_class, v]) => ({ asset_class, target_pct: parseFloat(v.replace(',', '.')) })),
      }),
    onClose,
  )
  return (
    <Modal title="Målfördelning" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        {CLASS_OPTIONS.map(([k, label]) => (
          <label key={k} className="flex items-center justify-between gap-3">
            <span>{label}</span>
            <span className="flex items-center gap-1">
              <input
                inputMode="decimal"
                className="w-20 text-right"
                value={current[k]}
                onChange={(e) => setValues({ ...current, [k]: e.target.value })}
              />
              %
            </span>
          </label>
        ))}
        <div className={`text-right text-xs ${Math.abs(total - 100) > 1 ? 'text-bad' : 'text-muted'}`}>
          Summa: {String(Math.round(total * 10) / 10).replace('.', ',')} % (ska bli 100 %)
        </div>
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={mutation.isPending || Math.abs(total - 100) > 1}
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

export function HoldingTargetsDialog({
  section,
  onClose,
}: {
  section: DriftAccountSection
  onClose: () => void
}) {
  const [values, setValues] = useState<Record<number, string>>(() =>
    Object.fromEntries(section.holdings.map((h) => [h.id, String(h.target_pct ?? 0)])),
  )
  const total = Object.values(values).reduce((s, v) => s + (parseFloat(v.replace(',', '.')) || 0), 0)
  const mutation = useApiMutation(
    () =>
      api.send('PUT', `/savings/accounts/${section.id}/targets`, {
        targets: section.holdings.map((h) => ({
          id: h.id,
          target_pct: parseFloat((values[h.id] ?? '0').replace(',', '.')) || 0,
        })),
      }),
    onClose,
  )
  return (
    <Modal title={`Målfördelning — ${section.name}`} onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        {section.holdings.map((h) => (
          <label key={h.id} className="flex items-center justify-between gap-3">
            <span>{h.name}</span>
            <span className="flex items-center gap-1">
              <input
                inputMode="decimal"
                className="w-20 text-right"
                value={values[h.id] ?? '0'}
                onChange={(e) => setValues((v) => ({ ...v, [h.id]: e.target.value }))}
              />
              %
            </span>
          </label>
        ))}
        <div className={`text-right text-xs ${Math.abs(total - 100) > 1 ? 'text-bad' : 'text-muted'}`}>
          Summa: {String(Math.round(total * 10) / 10).replace('.', ',')} % (ska bli 100 %)
        </div>
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={mutation.isPending || Math.abs(total - 100) > 1}
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
