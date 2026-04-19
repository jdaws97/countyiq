import type { ReactNode } from 'react'

import Nav from './Nav'

export default function PageShell({
  children,
  maxWidth = 900,
  padding = '48px 32px',
}: {
  children: ReactNode
  maxWidth?: number
  padding?: string
}) {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}>
      <Nav />
      <main style={{ maxWidth, margin: '0 auto', padding }}>{children}</main>
    </div>
  )
}
