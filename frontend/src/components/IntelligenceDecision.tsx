import { useIntelligenceWorkspace } from '../lib/intelligenceWorkspace'
import { WORK_LABELS } from '../lib/intelligenceFlow'
import type { EmergingCase, IntelligenceWorkItem } from '../types/emerging'
import { Button } from './ui'

export default function IntelligenceDecision({
  item,
  note,
}: {
  item: EmergingCase
  note?: string
}) {
  const { work, saveCase, storageMessage } = useIntelligenceWorkspace()
  const saved = work.find((entry) => entry.case_key === item.case_key)
  const actions: Array<[IntelligenceWorkItem['status'], string]> = [
    ['qualifying', 'Pursue'],
    ['waiting', 'Follow'],
    ['rejected', 'Dismiss'],
  ]
  return (
    <div className="intelligence-decision">
      <div className="emerging-save-actions" aria-label={`Decision for ${item.title}`}>
        {actions.map(([status, label]) => (
          <Button
            key={status}
            tone={saved?.status === status ? 'primary' : 'quiet'}
            aria-pressed={saved?.status === status}
            onClick={() => saveCase(item, status, note ?? saved?.note ?? '')}
          >
            {label}
          </Button>
        ))}
        {saved && <span role="status">{WORK_LABELS[saved.status]}</span>}
      </div>
      {storageMessage && <p role="status">{storageMessage}</p>}
    </div>
  )
}
