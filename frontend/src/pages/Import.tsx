import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, useAccounts, useInvalidate } from '../api/hooks'
import type { ImportPreview, InspectResult } from '../api/types'
import { AmountText } from '../components/AmountText'
import { formatDate, formatOre } from '../lib/format'

type Step =
  | { name: 'idle' }
  | { name: 'inspecting' }
  | { name: 'wizard'; file: File; result: InspectResult }
  | { name: 'previewing' }
  | { name: 'preview'; file: File; profileId: number; preview: ImportPreview }
  | { name: 'done'; inserted: number; duplicates: number; skipped: number; links: number }

const FIELD_LABELS: [string, string][] = [
  ['date', 'Datum'],
  ['description', 'Beskrivning'],
  ['amount', 'Belopp'],
  ['amount_in', 'Insättning (delad kolumn)'],
  ['amount_out', 'Uttag (delad kolumn)'],
  ['balance', 'Saldo'],
]

export function ImportPage() {
  const [step, setStep] = useState<Step>({ name: 'idle' })
  const [error, setError] = useState<string | null>(null)
  const invalidate = useInvalidate()

  const runPreview = useCallback(async (file: File, profileId: number) => {
    setStep({ name: 'previewing' })
    try {
      const preview = await api.sendFile<ImportPreview>('/import/preview', file, {
        profile_id: String(profileId),
      })
      setStep({ name: 'preview', file, profileId, preview })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStep({ name: 'idle' })
    }
  }, [])

  const inspect = useCallback(
    async (file: File) => {
      setError(null)
      setStep({ name: 'inspecting' })
      try {
        const result = await api.sendFile<InspectResult>('/import/inspect', file)
        if (result.known && result.profile && result.profile.default_account_id) {
          await runPreview(file, result.profile.id)
        } else {
          setStep({ name: 'wizard', file, result })
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
        setStep({ name: 'idle' })
      }
    },
    [runPreview],
  )

  async function commit(file: File, profileId: number) {
    try {
      const result = await api.sendFile<{
        inserted: number
        duplicates: number
        skipped: number
        suggested_links: number
      }>('/import/commit', file, { profile_id: String(profileId) })
      invalidate()
      setStep({
        name: 'done',
        inserted: result.inserted,
        duplicates: result.duplicates,
        skipped: result.skipped,
        links: result.suggested_links,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Importera transaktioner</h1>
        <Link to="/import/historik" className="text-sm text-accent hover:underline">
          Importhistorik →
        </Link>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-bad/40 bg-bad/10 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {(step.name === 'idle' || step.name === 'inspecting' || step.name === 'previewing') && (
        <Dropzone busy={step.name !== 'idle'} onFile={inspect} />
      )}

      {step.name === 'wizard' && (
        <MappingWizard
          file={step.file}
          result={step.result}
          onSaved={(profileId) => runPreview(step.file, profileId)}
          onCancel={() => setStep({ name: 'idle' })}
        />
      )}

      {step.name === 'preview' && (
        <PreviewView
          preview={step.preview}
          onCommit={() => commit(step.file, step.profileId)}
          onCancel={() => setStep({ name: 'idle' })}
        />
      )}

      {step.name === 'done' && (
        <div className="card px-6 py-10 text-center">
          <div className="text-4xl" aria-hidden>
            ✓
          </div>
          <h2 className="mt-3 text-lg font-semibold">Importen är klar</h2>
          <p className="mt-2 text-sm text-ink-2">
            {step.inserted} nya transaktioner importerades, {step.duplicates} dubbletter hoppades
            över{step.skipped > 0 && `, ${step.skipped} rader skippades`}.
            {step.links > 0 && (
              <>
                {' '}
                <Link to="/aterbetalningar" className="text-accent hover:underline">
                  {step.links} möjliga återbetalningspar hittades →
                </Link>
              </>
            )}
          </p>
          <div className="mt-5 flex justify-center gap-3">
            <button
              onClick={() => setStep({ name: 'idle' })}
              className="rounded-lg border border-baseline px-4 py-2 text-sm hover:bg-grid"
            >
              Importera fler
            </button>
            <Link
              to="/"
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
            >
              Till översikten
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

function Dropzone({ busy, onFile }: { busy: boolean; onFile: (f: File) => void }) {
  const [over, setOver] = useState(false)
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const f = e.dataTransfer.files[0]
        if (f) onFile(f)
      }}
      className={`card flex cursor-pointer flex-col items-center gap-3 border-2 border-dashed px-6 py-16 text-center transition-colors ${
        over ? 'border-accent bg-accent/5' : 'border-baseline'
      }`}
    >
      <span className="text-4xl" aria-hidden>
        {busy ? '⏳' : '⇪'}
      </span>
      <span className="text-lg font-medium">
        {busy ? 'Arbetar …' : 'Släpp en CSV- eller Excel-fil här'}
      </span>
      <span className="text-sm text-ink-2">
        Exportera från din bank (Swedbank, SEB, Nordea, Handelsbanken, ICA, Avanza, Amex …) och
        släpp filen här — eller klicka för att välja. Okända format får en guide första gången.
      </span>
      <input
        type="file"
        accept=".csv,.xlsx,.xls,.tsv,.txt"
        className="hidden"
        disabled={busy}
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
    </label>
  )
}

function MappingWizard({
  file,
  result,
  onSaved,
  onCancel,
}: {
  file: File
  result: InspectResult
  onSaved: (profileId: number) => void
  onCancel: () => void
}) {
  const insp = result.inspection
  const known = Boolean(result.known && result.profile)
  const { data: accounts = [] } = useAccounts()
  const [mapping, setMapping] = useState<Record<string, number | null>>(
    known ? result.profile!.column_mapping : insp.suggested_mapping,
  )
  const [name, setName] = useState(known ? result.profile!.name : suggestName(file.name))
  const [accountId, setAccountId] = useState<number | ''>(
    known && result.profile!.default_account_id ? result.profile!.default_account_id : '',
  )
  const [newAccountName, setNewAccountName] = useState('')
  const [invert, setInvert] = useState(
    known ? result.profile!.invert_sign : insp.suggested_invert_sign,
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const usedColumns = useMemo(
    () => new Map(Object.entries(mapping).filter(([, v]) => v !== null) as [string, number][]),
    [mapping],
  )

  async function save() {
    setError(null)
    if (mapping.date == null) return setError('Välj vilken kolumn som innehåller datum.')
    if (mapping.amount == null && mapping.amount_out == null)
      return setError('Välj en beloppskolumn (eller delade insättning/uttag-kolumner).')
    let acct = accountId
    setSaving(true)
    try {
      if (acct === '') {
        if (!newAccountName.trim()) {
          setSaving(false)
          return setError('Välj ett konto eller ange namn för ett nytt.')
        }
        const created = await api.send<{ id: number }>('POST', '/accounts', {
          name: newAccountName.trim(),
        })
        acct = created.id
      }
      const profile = await api.send<{ id: number }>('POST', '/import/profiles', {
        fingerprint: insp.fingerprint,
        name: name.trim() || suggestName(file.name),
        file_type: insp.file_type,
        column_mapping: mapping,
        default_account_id: acct,
        delimiter: insp.delimiter,
        encoding: insp.encoding,
        decimal_separator: insp.suggested_decimal_separator,
        thousands_separator: insp.suggested_thousands_separator,
        date_format: insp.suggested_date_format,
        header_row_index: insp.header_row_index,
        invert_sign: invert,
      })
      onSaved(profile.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setSaving(false)
    }
  }

  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold">
        {known ? 'Komplettera formatprofilen' : 'Nytt filformat — hjälp mig förstå kolumnerna'}
      </h2>
      <p className="mt-1 text-sm text-ink-2">
        {known
          ? 'Formatet känns igen men saknar standardkonto.'
          : 'Jag har gissat mappningen nedan utifrån rubrikerna. Justera vid behov — valen sparas och används automatiskt nästa gång du importerar en fil med samma format.'}
      </p>

      <div className="mt-4 overflow-x-auto rounded-lg border border-bord">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-bord text-left">
              {insp.header.map((h, i) => (
                <th key={i} className="px-3 py-2 font-medium">
                  <div className="text-xs text-muted">{h || `Kolumn ${i + 1}`}</div>
                  <select
                    className="mt-1 w-full text-xs"
                    value={[...usedColumns.entries()].find(([, col]) => col === i)?.[0] ?? ''}
                    onChange={(e) => {
                      const field = e.target.value
                      setMapping((m) => {
                        const next: Record<string, number | null> = { ...m }
                        for (const key of Object.keys(next)) if (next[key] === i) next[key] = null
                        if (field) next[field] = i
                        return next
                      })
                    }}
                  >
                    <option value="">Ignorera</option>
                    {FIELD_LABELS.map(([field, label]) => (
                      <option key={field} value={field}>
                        {label}
                      </option>
                    ))}
                  </select>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {insp.sample_rows.slice(0, 5).map((row, ri) => (
              <tr key={ri} className="border-b border-bord/50 last:border-0">
                {insp.header.map((_, ci) => (
                  <td key={ci} className="max-w-48 truncate px-3 py-1.5 text-ink-2">
                    {row[ci] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Profilnamn</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="t.ex. Swedbank privatkonto"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Importera till konto</span>
          <select
            value={accountId}
            onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : '')}
          >
            <option value="">+ Skapa nytt konto …</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          {accountId === '' && (
            <input
              value={newAccountName}
              onChange={(e) => setNewAccountName(e.target.value)}
              placeholder="Namn på nytt konto, t.ex. Lönekonto"
            />
          )}
        </label>
      </div>

      <label className="mt-4 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={invert}
          onChange={(e) => setInvert(e.target.checked)}
          className="h-4 w-4"
        />
        <span>
          Vänd tecken — kryssa i för kreditkort som listar köp som positiva belopp
          {insp.suggested_invert_sign && ' (rekommenderas för denna fil)'}
        </span>
      </label>

      {error && <div className="mt-3 text-sm text-bad">{error}</div>}

      <div className="mt-5 flex justify-end gap-3">
        <button
          onClick={onCancel}
          className="rounded-lg border border-baseline px-4 py-2 text-sm hover:bg-grid"
        >
          Avbryt
        </button>
        <button
          onClick={save}
          disabled={saving}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {saving ? 'Sparar …' : 'Spara & förhandsgranska'}
        </button>
      </div>
    </div>
  )
}

function PreviewView({
  preview,
  onCommit,
  onCancel,
}: {
  preview: ImportPreview
  onCommit: () => void
  onCancel: () => void
}) {
  const [showDuplicates, setShowDuplicates] = useState(false)
  const rows = showDuplicates ? preview.rows : preview.rows.filter((r) => !r.duplicate)
  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold">Förhandsgranskning — {preview.profile_name}</h2>

      {preview.identical_file_already_imported && (
        <div className="mt-3 rounded-lg border border-series-4/60 bg-series-4/10 px-4 py-2.5 text-sm">
          ⚠ Exakt denna fil verkar redan vara importerad.
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-3">
        <Badge label="nya" value={preview.new_count} tone="good" />
        <Badge label="dubbletter" value={preview.duplicate_count} tone="muted" />
        <Badge label="auto-kategoriserade" value={preview.auto_categorized} tone="accent" />
        {preview.skipped.length > 0 && (
          <Badge label="skippade rader" value={preview.skipped.length} tone="warn" />
        )}
      </div>

      <label className="mt-4 flex items-center gap-2 text-sm text-ink-2">
        <input
          type="checkbox"
          checked={showDuplicates}
          onChange={(e) => setShowDuplicates(e.target.checked)}
          className="h-4 w-4"
        />
        Visa även dubbletter
      </label>

      <div className="mt-3 max-h-96 overflow-y-auto rounded-lg border border-bord">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr className="border-b border-bord text-left text-xs text-muted">
              <th className="px-3 py-2">Datum</th>
              <th className="px-3 py-2">Beskrivning</th>
              <th className="px-3 py-2 text-right">Belopp</th>
              <th className="px-3 py-2">Kategori</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={i}
                className={`border-b border-bord/50 last:border-0 ${r.duplicate ? 'opacity-45' : ''}`}
              >
                <td className="whitespace-nowrap px-3 py-1.5 text-ink-2">
                  {formatDate(r.booked_date)}
                </td>
                <td className="max-w-md truncate px-3 py-1.5">
                  {r.description}
                  {r.duplicate && <span className="ml-2 text-xs text-muted">(dubblett)</span>}
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 text-right">
                  <AmountText ore={r.amount_ore} decimals />
                </td>
                <td className="whitespace-nowrap px-3 py-1.5 text-xs text-ink-2">
                  {r.category_name ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-5 flex items-center justify-between">
        <span className="text-sm text-ink-2">
          Netto för nya rader:{' '}
          {formatOre(preview.rows.filter((r) => !r.duplicate).reduce((s, r) => s + r.amount_ore, 0))}
        </span>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="rounded-lg border border-baseline px-4 py-2 text-sm hover:bg-grid"
          >
            Avbryt
          </button>
          <button
            onClick={onCommit}
            disabled={preview.new_count === 0}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Importera {preview.new_count} transaktioner
          </button>
        </div>
      </div>
    </div>
  )
}

function Badge({ label, value, tone }: { label: string; value: number; tone: string }) {
  const cls =
    tone === 'good'
      ? 'bg-good/10 text-good'
      : tone === 'accent'
        ? 'bg-accent/10 text-accent'
        : tone === 'warn'
          ? 'bg-series-4/15 text-ink'
          : 'bg-grid text-ink-2'
  return (
    <span className={`rounded-full px-3 py-1 text-sm font-medium ${cls}`}>
      {value} {label}
    </span>
  )
}

function suggestName(filename: string): string {
  const base = filename.replace(/\.[^.]+$/, '')
  const lower = base.toLowerCase()
  for (const [needle, name] of [
    ['swedbank', 'Swedbank'],
    ['seb', 'SEB'],
    ['nordea', 'Nordea'],
    ['handelsbanken', 'Handelsbanken'],
    ['ica', 'ICA Banken'],
    ['avanza', 'Avanza'],
    ['amex', 'American Express'],
    ['entercard', 'Entercard Mastercard'],
  ] as const) {
    if (lower.includes(needle)) return name
  }
  return base
}
