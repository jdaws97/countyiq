import type { CSSProperties, ReactNode } from 'react'

/**
 * A small status pill. `color` is any CSS colour, normally a theme token such
 * as `var(--accent-green)`; the tint and border are derived with color-mix in
 * theme.css so the pill stays legible in both themes. (The previous
 * `${color}20` hex-alpha trick silently produced no background for token
 * colours.)
 */
export default function Badge({ color, mono = false, children }: { color: string; mono?: boolean; children: ReactNode }) {
  return (
    <span className={`badge${mono ? ' badge-mono' : ''}`} style={{ '--badge-color': color } as CSSProperties}>
      {children}
    </span>
  )
}
