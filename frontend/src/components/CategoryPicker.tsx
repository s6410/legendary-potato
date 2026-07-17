import { useCategories } from '../api/hooks'
import type { Category } from '../api/types'

interface Props {
  value: number | null
  onChange: (id: number | null) => void
  allowEmpty?: boolean
  emptyLabel?: string
  kinds?: string[]
  className?: string
}

/** Tvånivåväljare för kategori (optgroup per huvudkategori). */
export function CategoryPicker({
  value,
  onChange,
  allowEmpty = true,
  emptyLabel = 'Alla kategorier',
  kinds,
  className = '',
}: Props) {
  const { data: tree = [] } = useCategories()
  const roots = kinds ? tree.filter((c: Category) => kinds.includes(c.kind)) : tree
  return (
    <select
      className={className}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      {allowEmpty && <option value="">{emptyLabel}</option>}
      {roots.map((root: Category) => (
        <optgroup key={root.id} label={root.name}>
          <option value={root.id}>{root.name}</option>
          {root.children.map((child) => (
            <option key={child.id} value={child.id}>
              {'  '}
              {child.name}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}
