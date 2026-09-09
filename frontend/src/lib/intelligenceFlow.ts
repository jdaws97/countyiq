import type {
  ActionReadiness,
  EmergingCaseSummary,
  IntelligenceOpportunitySummary,
  IntelligenceProfile,
  IntelligenceWorkItem,
  ProjectType,
} from '../types/emerging'

export const PROJECT_TYPES: ProjectType[] = [
  'industrial',
  'logistics',
  'housing',
  'mixed_use',
  'commercial',
  'infrastructure',
]
export const READINESS: Array<[ActionReadiness, string]> = [
  ['research', 'Early research'],
  ['qualify', 'Work to qualify'],
  ['act', 'Ready for action'],
  ['wait', 'Waiting on a milestone'],
]
export const WORK_LABELS: Record<IntelligenceWorkItem['status'], string> = {
  saved: 'Saved',
  qualifying: 'Pursuing',
  waiting: 'Following',
  acted: 'Action taken',
  rejected: 'Dismissed',
}

export function matchingPossibilities<T extends IntelligenceOpportunitySummary>(
  item: { opportunities: T[]; implications: T[] },
  profile: IntelligenceProfile,
  qualifiedOnly = false,
) {
  const possibilities = qualifiedOnly
    ? item.opportunities
    : [...item.opportunities, ...item.implications]
  const services = profile.audience === 'investor' ? [] : profile.services
  return possibilities.filter(
    (possibility) =>
      (profile.audience === 'all' || possibility.audience === profile.audience) &&
      (!services.length || possibility.services.some((service) => services.includes(service))) &&
      (!profile.preferred_readiness?.length ||
        profile.preferred_readiness.includes(possibility.readiness)),
  )
}

export function profileQuery(profile: IntelligenceProfile): URLSearchParams {
  const params = new URLSearchParams()
  if (profile.audience !== 'all') {
    params.set('audience', profile.audience)
  }
  for (const [key, values] of [
    ['service', profile.audience === 'investor' ? [] : profile.services],
    ['family', profile.families],
    ['municipality', profile.municipalities],
    ['project_type', profile.project_types ?? []],
    ['readiness', profile.preferred_readiness ?? []],
  ] as Array<[string, string[]]>) {
    for (const value of values) {
      params.append(key, value)
    }
  }
  return params
}

export function caseFit(item: EmergingCaseSummary, profile: IntelligenceProfile): string {
  if (
    profile.municipalities.length &&
    !item.municipalities.some((place) =>
      profile.municipalities.some((selected) => selected.toLowerCase() === place.toLowerCase()),
    )
  ) {
    return 'Outside your selected area.'
  }
  if (
    profile.project_types?.length &&
    !item.project_types.some((type) => profile.project_types?.includes(type))
  ) {
    return item.project_types.length
      ? 'Outside your selected project types.'
      : 'The project type has not been established for your criteria.'
  }
  if (profile.families.length && !profile.families.includes(item.family)) {
    return 'Outside the changes you chose to follow.'
  }
  const possibilities = matchingPossibilities(item, profile)
  if (
    !possibilities.length &&
    (profile.audience !== 'all' || profile.services.length || profile.preferred_readiness?.length)
  ) {
    return 'No commercial fit is currently established for your selected work and timing.'
  }
  if (matchingPossibilities(item, profile, true).length) {
    return 'A specific commercial possibility matches your work. Review its timing and qualification route.'
  }
  if (profile.audience !== 'all' || profile.services.length) {
    return 'Relevant to your interests at a research stage. A commercial action is not yet established.'
  }
  return 'Set your work criteria to see its relevance to your business.'
}

export function workNeedsReview(
  item: IntelligenceWorkItem,
  current?: Pick<EmergingCaseSummary, 'revision'>,
): boolean {
  return item.status !== 'rejected' && (!current || current.revision !== item.last_seen_revision)
}
