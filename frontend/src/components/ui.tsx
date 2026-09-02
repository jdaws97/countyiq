import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'

type ButtonTone = 'primary' | 'secondary' | 'quiet' | 'danger'

export function Button({
  tone = 'secondary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: ButtonTone }) {
  return <button className={`ciq-button ciq-button-${tone} ${className}`.trim()} {...props} />
}

export function ButtonLink({
  tone = 'secondary',
  className = '',
  ...props
}: LinkProps & { tone?: ButtonTone }) {
  return <Link className={`ciq-button ciq-button-${tone} ${className}`.trim()} {...props} />
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  meta,
}: {
  eyebrow?: string
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  meta?: ReactNode
}) {
  return (
    <header className="page-header">
      <div className="page-header-copy">
        {eyebrow && <div className="page-eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
        {meta && <div className="page-header-meta">{meta}</div>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  )
}

export function EmptyState({
  title,
  children,
  actions,
}: {
  title: string
  children: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="empty-state">
      <div className="empty-state-mark" aria-hidden="true">◎</div>
      <h2>{title}</h2>
      <div className="empty-state-copy">{children}</div>
      {actions && <div className="empty-state-actions">{actions}</div>}
    </div>
  )
}

export function StatusMessage({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'error' | 'success'
}) {
  return <div className={`status-message status-message-${tone}`}>{children}</div>
}

export function Freshness({ value, label = 'Evidence current through' }: { value?: string | null; label?: string }) {
  if (!value) return null
  const date = new Date(value)
  const rendered = Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  return <span className="freshness-label">{label} {rendered}</span>
}
