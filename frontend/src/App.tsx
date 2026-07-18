import { NavLink, Outlet } from 'react-router-dom'

import { useLinkSuggestions } from './api/hooks'
import { CommandPalette } from './components/CommandPalette'
import { setTheme, useTheme } from './lib/theme'

const NAV = [
  { to: '/', label: 'Översikt', icon: '◈' },
  { to: '/transaktioner', label: 'Transaktioner', icon: '☰' },
  { to: '/import', label: 'Importera', icon: '⇪' },
  { to: '/aterbetalningar', label: 'Återbetalningar', icon: '⇄' },
  { to: '/prenumerationer', label: 'Prenumerationer', icon: '↻' },
  { to: '/hushall', label: 'Hushåll', icon: '⚭' },
  { to: '/budget', label: 'Budget', icon: '◔' },
  { to: '/sparande', label: 'Sparande', icon: '⛁' },
  { to: '/rapport', label: 'Månadsrapport', icon: '▤' },
  { to: '/kategorier', label: 'Kategorier', icon: '⊞' },
  { to: '/regler', label: 'Regler', icon: '⚙' },
  { to: '/installningar', label: 'Inställningar', icon: '…' },
]

export default function App() {
  const { pref, mode } = useTheme()
  const { data: suggestions = [] } = useLinkSuggestions()

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-bord bg-surface px-3 py-4">
        <div className="mb-6 flex items-center gap-2 px-2">
          <span className="text-xl" aria-hidden>
            📒
          </span>
          <span className="text-lg font-bold tracking-tight">Kassaboken</span>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-accent/10 font-medium text-accent'
                    : 'text-ink-2 hover:bg-grid hover:text-ink'
                }`
              }
            >
              <span className="w-4 text-center" aria-hidden>
                {item.icon}
              </span>
              {item.label}
              {item.to === '/aterbetalningar' && suggestions.length > 0 && (
                <span className="ml-auto rounded-full bg-accent px-1.5 text-xs font-semibold text-white">
                  {suggestions.length}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="mt-4 flex flex-col gap-1">
          <span className="px-3 text-xs text-muted">Ctrl+K för kommandon</span>
          <button
            onClick={() => setTheme(mode === 'dark' ? 'light' : 'dark')}
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink-2 hover:bg-grid"
            title={pref === 'system' ? 'Följer systemet' : undefined}
          >
            {mode === 'dark' ? '☀ Ljust läge' : '☾ Mörkt läge'}
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-6 py-6 lg:px-8">
        <Outlet />
      </main>
      <CommandPalette />
    </div>
  )
}
