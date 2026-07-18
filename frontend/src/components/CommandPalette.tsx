import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { formatMonth, shiftMonth, currentMonth } from '../lib/format'
import { setTheme, useTheme } from '../lib/theme'

interface Command {
  id: string
  label: string
  hint?: string
  keywords: string
  run: () => void
}

/** Global kommandopalett: Ctrl/Cmd+K. Navigation, månadshopp, sök, tema. */
export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [index, setIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const { mode } = useTheme()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
        setQuery('')
        setIndex(0)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => {
      navigate(to)
      setOpen(false)
    }
    const nav: Command[] = [
      { id: 'oversikt', label: 'Gå till Översikt', keywords: 'översikt dashboard hem', run: go('/') },
      { id: 'transaktioner', label: 'Gå till Transaktioner', keywords: 'transaktioner lista', run: go('/transaktioner') },
      { id: 'import', label: 'Importera fil', keywords: 'import csv excel pdf fil', run: go('/import') },
      { id: 'aterbetalningar', label: 'Gå till Återbetalningar', keywords: 'återbetalningar kvittning par', run: go('/aterbetalningar') },
      { id: 'prenumerationer', label: 'Gå till Prenumerationer', keywords: 'prenumerationer abonnemang återkommande', run: go('/prenumerationer') },
      { id: 'hushall', label: 'Gå till Hushåll', keywords: 'hushåll medlem vem avräkning', run: go('/hushall') },
      { id: 'budget', label: 'Gå till Budget', keywords: 'budget', run: go('/budget') },
      { id: 'sparande', label: 'Gå till Sparande', keywords: 'sparande drift rebalansering', run: go('/sparande') },
      { id: 'rapport', label: 'Öppna Månadsrapport', keywords: 'rapport månad', run: go('/rapport') },
      {
        id: 'arsrapport',
        label: `Öppna Årsrapport ${new Date().getFullYear()}`,
        keywords: 'årsrapport år ditt ekonomiska år wrapped',
        run: go(`/rapport/ar/${new Date().getFullYear()}`),
      },
      { id: 'kategorier', label: 'Gå till Kategorier', keywords: 'kategorier', run: go('/kategorier') },
      { id: 'regler', label: 'Gå till Regler', keywords: 'regler kategorisering', run: go('/regler') },
      { id: 'installningar', label: 'Gå till Inställningar', keywords: 'inställningar konton tema medlemmar', run: go('/installningar') },
      {
        id: 'tema',
        label: mode === 'dark' ? 'Byt till ljust läge' : 'Byt till mörkt läge',
        keywords: 'tema mörkt ljust dark light',
        run: () => {
          setTheme(mode === 'dark' ? 'light' : 'dark')
          setOpen(false)
        },
      },
    ]
    // månadshopp: senaste 24 månaderna
    const now = currentMonth()
    for (let i = 0; i < 24; i++) {
      const m = shiftMonth(now, -i)
      nav.push({
        id: `manad-${m}`,
        label: `Visa ${formatMonth(m, true)}`,
        hint: 'månadsrapport',
        keywords: `månad ${formatMonth(m, true)} ${m}`,
        run: go(`/rapport/${m}`),
      })
    }
    return nav
  }, [navigate, mode])

  const q = query.trim().toLowerCase()
  const filtered = useMemo(() => {
    const base = q
      ? commands.filter(
          (c) => c.label.toLowerCase().includes(q) || c.keywords.toLowerCase().includes(q),
        )
      : commands.slice(0, 12)
    return base.slice(0, 12)
  }, [commands, q])

  const searchCommand: Command | null = q
    ? {
        id: 'sok',
        label: `Sök transaktioner: "${query.trim()}"`,
        keywords: '',
        run: () => {
          navigate(`/transaktioner?q=${encodeURIComponent(query.trim())}`)
          setOpen(false)
        },
      }
    : null
  const items = searchCommand ? [...filtered, searchCommand] : filtered

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh]"
      onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}
    >
      <div className="card w-full max-w-lg overflow-hidden shadow-2xl">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setIndex(0)
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setIndex((i) => Math.min(items.length - 1, i + 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setIndex((i) => Math.max(0, i - 1))
            } else if (e.key === 'Enter' && items[index]) {
              items[index].run()
            }
          }}
          placeholder="Skriv ett kommando eller sök …"
          className="w-full rounded-none border-0 border-b border-bord px-4 py-3 text-base focus-visible:outline-none"
        />
        <ul className="max-h-80 overflow-y-auto py-1">
          {items.map((c, i) => (
            <li key={c.id}>
              <button
                onClick={c.run}
                onMouseEnter={() => setIndex(i)}
                className={`flex w-full items-center justify-between px-4 py-2 text-left text-sm ${
                  i === index ? 'bg-accent/10 text-accent' : ''
                }`}
              >
                <span>{c.label}</span>
                {c.hint && <span className="text-xs text-muted">{c.hint}</span>}
              </button>
            </li>
          ))}
          {items.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-muted">Inga träffar.</li>
          )}
        </ul>
        <div className="border-t border-bord px-4 py-1.5 text-xs text-muted">
          ↑↓ navigera · Enter välj · Esc stäng
        </div>
      </div>
    </div>
  )
}
