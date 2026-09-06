import type { ReactNode } from 'react'

import Nav from './Nav'

export default function PageShell({
  children,
  maxWidth = 900,
}: {
  children: ReactNode
  maxWidth?: number
}) {
  return (
    <div className="page-shell">
      <Nav />
      <main className="page-shell-main" style={{ maxWidth }}>
        {children}
      </main>
    </div>
  )
}
