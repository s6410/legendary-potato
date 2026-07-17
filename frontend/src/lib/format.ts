// Svensk formattering av belopp (ören → kr) och datum, samlad på ett ställe.

const kr0 = new Intl.NumberFormat('sv-SE', {
  style: 'currency',
  currency: 'SEK',
  maximumFractionDigits: 0,
})

const kr2 = new Intl.NumberFormat('sv-SE', {
  style: 'currency',
  currency: 'SEK',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export function formatOre(ore: number | null | undefined, decimals = false): string {
  if (ore == null) return '–'
  return (decimals ? kr2 : kr0).format(ore / 100)
}

export function formatSigned(ore: number | null | undefined): string {
  if (ore == null) return '–'
  const s = formatOre(ore)
  return ore > 0 ? `+${s}` : s
}

export function formatPct(value: number | null | undefined, decimals = 0): string {
  if (value == null) return '–'
  return `${(value * 100).toFixed(decimals).replace('.', ',')} %`
}

const monthFmt = new Intl.DateTimeFormat('sv-SE', { month: 'short', year: 'numeric' })
const monthLong = new Intl.DateTimeFormat('sv-SE', { month: 'long', year: 'numeric' })
const dateFmt = new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'short' })

export function formatMonth(month: string, long = false): string {
  const d = new Date(`${month}-01T12:00:00`)
  return (long ? monthLong : monthFmt).format(d)
}

export function formatDate(iso: string): string {
  return dateFmt.format(new Date(`${iso}T12:00:00`))
}

export function currentMonth(): string {
  return new Date().toISOString().slice(0, 7)
}

export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split('-').map(Number)
  const total = y * 12 + (m - 1) + delta
  const ny = Math.floor(total / 12)
  const nm = (total % 12) + 1
  return `${ny}-${String(nm).padStart(2, '0')}`
}
