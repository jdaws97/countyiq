import type { EvidenceItem, IntelligenceEvent, RecordDate } from '../types/api'

export function investigationDetails(event: IntelligenceEvent) {
  const proceeding = event.sources.find((source) =>
    [2, 3].includes(Number(source.details?.contract_version)),
  )?.details
  const details =
    event.sources.find((source) => Number(source.details?.explanation_version) === 1)?.details ??
    proceeding
  const dates: RecordDate[] = Array.isArray(details?.record_dates)
    ? details.record_dates.filter(
        (value): value is RecordDate =>
          Boolean(value) &&
          typeof value === 'object' &&
          typeof value.label === 'string' &&
          typeof value.status === 'string',
      )
    : []
  const nextStep =
    typeof details?.explanation_next_step === 'string' ? details.explanation_next_step : null
  const conditions = Array.isArray(proceeding?.conditions)
    ? proceeding.conditions.flatMap((value, index) =>
        typeof value === 'string' && value.trim() ? [{ text: value, index }] : [],
      )
    : []
  const milestones = Array.isArray(proceeding?.milestones)
    ? proceeding.milestones.flatMap((value, index) =>
        value && typeof value === 'object' && typeof value.text === 'string' && value.text.trim()
          ? [{ text: value.text, kind: typeof value.kind === 'string' ? value.kind : null, index }]
          : [],
      )
    : []
  return { dates, nextStep, conditions, milestones }
}

export function supportingSource(
  event: IntelligenceEvent,
  marker: string,
): EvidenceItem | undefined {
  return event.sources.find(
    (source) => Array.isArray(source.details?.supports) && source.details.supports.includes(marker),
  )
}

export function activityLabel(event: IntelligenceEvent): string {
  if (event.matter?.readiness && event.matter.readiness !== 'ready') {
    return 'Research lead'
  }
  if (event.matter?.outcome && event.matter.outcome !== 'not_established') {
    if (event.matter.outcome === 'approved' && event.event_type === 'update') {
      return 'Approval reported'
    }
    const labels = {
      continued: 'Continued',
      approved: 'Approved',
      conditional: 'Approved with conditions',
      denied: 'Denied',
      withdrawn: 'Withdrawn',
      mixed: 'Partial decision',
    }
    return labels[event.matter.outcome]
  }
  if (event.event_type === 'scoped_decision') {
    const scope = event.sources.find((source) => typeof source.details?.decision_scope === 'string')
      ?.details.decision_scope
    if (typeof scope === 'string') {
      return `${scope.replace(/_/g, ' ')} decision`
    }
  }
  if (event.event_type === 'upcoming_decision') {
    return 'Proposed action'
  }
  if (event.event_type === 'municipal_record') {
    return 'Research lead'
  }
  return event.event_type.replace(/_/g, ' ')
}
