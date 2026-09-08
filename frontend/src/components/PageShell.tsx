import type { ReactNode } from 'react'

import WorkspaceShell from './WorkspaceShell'

export default function PageShell({
  children,
  maxWidth = 900,
  className,
  wide = false,
}: {
  children: ReactNode
  maxWidth?: number
  className?: string
  wide?: boolean
}) {
  return (
    <WorkspaceShell className={className} maxWidth={maxWidth} wide={wide}>
      {children}
    </WorkspaceShell>
  )
}
