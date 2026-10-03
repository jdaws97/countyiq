import { Button } from '../ui'

type InquiryActionsProps = {
  busy: boolean
  canSave: boolean
  canPreview: boolean
  onSave: () => void
  onPreview: () => void
}

export default function InquiryActions({
  busy,
  canSave,
  canPreview,
  onSave,
  onPreview,
}: InquiryActionsProps) {
  return (
    <div className="site-review-actions">
      <Button tone="primary" onClick={onSave} disabled={busy || !canSave}>
        Save inquiry
      </Button>
      <Button onClick={onPreview} disabled={busy || !canPreview}>
        {busy ? 'Checking evidence…' : 'Preview handoff'}
      </Button>
    </div>
  )
}
