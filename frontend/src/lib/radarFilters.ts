export type RadarPlanStatus = 'any' | 'active' | 'none'

export function planStatusFor(view: string, value: string | null): RadarPlanStatus {
  if (value === 'any' || value === 'active' || value === 'none') {
    return value
  }
  return view === 'opportunity' ? 'none' : 'any'
}

export function appendRadarCriteria(
  params: URLSearchParams,
  criteria: {
    minScore: string
    municipality: string
    minAcres: string
    maxAcres: string
    parcelClass: string
    planStatus: RadarPlanStatus
  },
) {
  params.set('min_score', criteria.minScore)
  params.set('plan_status', criteria.planStatus)
  if (criteria.municipality) {
    params.set('municipality', criteria.municipality)
  }
  if (criteria.minAcres) {
    params.set('min_acres', criteria.minAcres)
  }
  if (criteria.maxAcres) {
    params.set('max_acres', criteria.maxAcres)
  }
  if (criteria.parcelClass) {
    params.set('class', criteria.parcelClass)
  }
  return params
}
