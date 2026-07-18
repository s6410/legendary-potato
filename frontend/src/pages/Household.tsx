import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { useByMember, useTransactions } from '../api/hooks'
import { AmountText } from '../components/AmountText'
import { EmptyState } from '../components/EmptyState'
import { PeriodPicker } from '../components/PeriodPicker'
import { currentMonth, formatOre } from '../lib/format'

export function HouseholdPage() {
  const [month, setMonth] = useState(currentMonth())
  const { data, isLoading } = useByMember({ period: month })

  // hoppa till senaste månaden med data om innevarande är tom (max en gång)
  const { data: anyTxns } = useTransactions({ page_size: 1 })
  const touched = useRef(false)
  useEffect(() => {
    const latest = anyTxns?.rows[0]?.booked_date.slice(0, 7)
    if (!touched.current && latest && latest < currentMonth()) {
      touched.current = true
      setMonth(latest)
    }
  }, [anyTxns])

  const members = data?.members ?? []
  const maxExpense = Math.max(...members.map((m) => Math.abs(m.expenses_ore)), 1)

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Hushåll</h1>
        <PeriodPicker
          month={month}
          onChange={(m) => {
            touched.current = true
            setMonth(m)
          }}
        />
      </div>
      <p className="mb-5 text-sm text-ink-2">
        Vem står för utgifterna? Medlem sätts automatiskt från kortexporter med ägarkolumn
        (t.ex. Handelsbanken) och manuellt för kontotransaktioner — markera rader i
        transaktionslistan och välj "Sätt medlem".
      </p>

      {!isLoading && members.length === 0 ? (
        <EmptyState icon="⚭" title="Inga medlemmar ännu" actionLabel="Till transaktionerna" actionTo="/transaktioner">
          Importera en kortexport med ägarkolumn, eller markera transaktioner och sätt medlem
          manuellt, så visas fördelningen här.
        </EmptyState>
      ) : (
        <>
          <div className="flex flex-col gap-3">
            {members.map((m) => (
              <Link
                key={m.member}
                to={`/transaktioner?member=${encodeURIComponent(m.member!)}&from=${month}-01`}
                className="card block p-4 transition-colors hover:bg-grid/40"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{m.member}</span>
                  <span className="text-sm text-ink-2">
                    {m.transaction_count} transaktioner
                    {m.income_ore > 0 && (
                      <>
                        {' '}
                        · inkomster <AmountText ore={m.income_ore} />
                      </>
                    )}
                  </span>
                </div>
                <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-grid">
                  <div
                    className="h-full rounded-full bg-series-7"
                    style={{ width: `${(Math.abs(m.expenses_ore) / maxExpense) * 100}%` }}
                  />
                </div>
                <div className="mt-1 text-sm tabular text-ink-2">
                  Utgifter: {formatOre(Math.abs(m.expenses_ore))}
                </div>
              </Link>
            ))}

            {data?.unassigned && data.unassigned.transaction_count > 0 && (
              <Link
                to={`/transaktioner?member=__none__&from=${month}-01`}
                className="card block p-4 opacity-70 transition-colors hover:bg-grid/40"
              >
                <div className="flex items-center justify-between text-sm">
                  <span>Utan medlem</span>
                  <span className="text-ink-2">
                    {data.unassigned.transaction_count} transaktioner ·{' '}
                    {formatOre(Math.abs(data.unassigned.expenses_ore))}
                  </span>
                </div>
              </Link>
            )}
          </div>

          {data && data.settlement.length >= 2 && (
            <div className="card mt-6 p-5">
              <h2 className="font-semibold">Avräkning — om ni delar lika</h2>
              <p className="mt-1 text-xs text-muted">
                Jämför vad var och en faktiskt betalat mot en jämn delning av periodens utgifter.
              </p>
              <ul className="mt-3 flex flex-col gap-1.5 text-sm">
                {data.settlement.map((s) => (
                  <li key={s.member} className="flex items-center justify-between">
                    <span>{s.member}</span>
                    <span className="tabular">
                      betalat {formatOre(s.paid_ore)} ·{' '}
                      {s.diff_ore > 0 ? (
                        <span className="text-good">ligger ute med {formatOre(s.diff_ore)}</span>
                      ) : s.diff_ore < 0 ? (
                        <span>skyldig {formatOre(-s.diff_ore)}</span>
                      ) : (
                        'jämnt'
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  )
}
