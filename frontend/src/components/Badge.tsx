import type { ReactNode } from 'react'

export default function Badge({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '3px 10px',
        borderRadius: 4,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        fontWeight: 600,
        color,
        background: `${color}20`,
        border: `1px solid ${color}40`,
      }}
    >
      {children}
    </span>
  )
}
