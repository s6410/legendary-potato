import { formatOre } from '../lib/format'

interface Props {
  ore: number | null | undefined
  signed?: boolean
  decimals?: boolean
  className?: string
}

/** Belopp med teckenfärg: positiva gröna, negativa i vanlig ink (utgifter är normalläget). */
export function AmountText({ ore, signed = true, decimals = false, className = '' }: Props) {
  if (ore == null) return <span className={`text-muted ${className}`}>–</span>
  const color = signed && ore > 0 ? 'text-good' : 'text-ink'
  const prefix = signed && ore > 0 ? '+' : ''
  return (
    <span className={`tabular ${color} ${className}`}>
      {prefix}
      {formatOre(ore, decimals)}
    </span>
  )
}
