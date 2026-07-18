import { useSyncExternalStore } from 'react'

type Theme = 'light' | 'dark' | 'system'

const listeners = new Set<() => void>()

function resolved(pref: Theme): 'light' | 'dark' {
  if (pref === 'system') {
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return pref
}

export function getThemePref(): Theme {
  const t = localStorage.getItem('theme')
  return t === 'dark' || t === 'light' ? t : 'system'
}

export function setTheme(pref: Theme) {
  if (pref === 'system') localStorage.removeItem('theme')
  else localStorage.setItem('theme', pref)
  document.documentElement.classList.toggle('dark', resolved(pref) === 'dark')
  listeners.forEach((l) => l())
}

matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (getThemePref() === 'system') setTheme('system')
})

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

// snapshotten måste ändra värde även när bara det UPPLÖSTA läget ändras
// (pref='system' + OS-byte), annars bailar React och diagrammen behåller
// gamla färger
function snapshot(): string {
  const pref = getThemePref()
  return `${pref}:${resolved(pref)}`
}

export function useTheme(): { pref: Theme; mode: 'light' | 'dark' } {
  const snap = useSyncExternalStore(subscribe, snapshot)
  const [pref, mode] = snap.split(':') as [Theme, 'light' | 'dark']
  return { pref, mode }
}

/** Läs aktuella CSS-variabler för diagram (ECharts kan inte läsa var()). */
export function chartTokens() {
  const s = getComputedStyle(document.documentElement)
  const v = (name: string) => s.getPropertyValue(name).trim()
  return {
    surface: v('--surface-1'),
    ink: v('--ink'),
    ink2: v('--ink-2'),
    muted: v('--muted'),
    grid: v('--grid'),
    baseline: v('--baseline'),
    good: v('--good'),
    bad: v('--bad'),
    accent: v('--accent'),
    series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v(`--series-${i}`)),
  }
}
