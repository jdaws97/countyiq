import { useEffect, useRef } from 'react'
import { Button, StatusMessage } from '../ui'

type Props = {
  error: string
  onStay: () => void
  onDiscard: () => void
  onSave: () => void
}

export default function UnsavedInquiryDialog({ error, onStay, onDiscard, onSave }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])
  return (
    <dialog
      ref={dialog}
      className="site-unsaved-dialog"
      aria-labelledby="unsaved-inquiry-title"
      onCancel={(event) => {
        event.preventDefault()
        onStay()
      }}
    >
      <h2 id="unsaved-inquiry-title">Keep your inquiry changes?</h2>
      <p>Your notes have not been saved. Save them before continuing, or stay here to finish.</p>
      {error && <StatusMessage tone="error">{error}</StatusMessage>}
      <div className="site-toolbar">
        <Button tone="primary" onClick={onSave}>
          Save and continue
        </Button>
        <Button onClick={onStay}>Stay here</Button>
        <Button tone="quiet" onClick={onDiscard}>
          Discard changes
        </Button>
      </div>
    </dialog>
  )
}
