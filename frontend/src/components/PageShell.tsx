import type { ReactNode } from 'react'

import Nav from './Nav'

export default function PageShell({
  children,
  maxWidth = 900,
  padding,
}: {
  children: ReactNode
  maxWidth?: number
  padding?: string
}) {
  return (
    <div className="page-shell">
      <Nav />
      <main className="page-shell-main" style={{ maxWidth, ...(padding ? { padding } : {}) }}>{children}</main>
    </div>
  )
}
