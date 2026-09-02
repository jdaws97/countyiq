import type { ReactNode } from 'react'

export default function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="content-section">
      <h2 className="content-section-title">{title}</h2>
      {children}
    </section>
  )
}
