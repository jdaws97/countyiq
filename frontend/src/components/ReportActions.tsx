import { useState } from 'react'

import { Button } from './ui'

export default function ReportActions({ label }: { label: string }) {
  const [copied, setCopied] = useState(false)

  const share = async () => {
    const payload = { title: label, text: `${label} — CountyIQ`, url: window.location.href }
    try {
      if (navigator.share) {
        await navigator.share(payload)
      } else {
        await navigator.clipboard.writeText(window.location.href)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1800)
      }
    } catch {
      // A cancelled share sheet is not an application error.
    }
  }

  return (
    <div className="report-actions" data-print-hidden>
      <Button tone="quiet" type="button" onClick={share}>{copied ? 'Link copied' : 'Share'}</Button>
      <Button tone="quiet" type="button" onClick={() => window.print()}>Print / Save PDF</Button>
    </div>
  )
}
