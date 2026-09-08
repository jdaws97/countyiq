import { workspaceStorageKey } from './browserStorage'
import type { IntelligenceProfile, IntelligenceWorkItem } from '../types/emerging'

const PROFILE_KEY = 'countyiq_intelligence_profile_v1'
const WORK_KEY = 'countyiq_intelligence_work_v1'
export const DEFAULT_INTELLIGENCE_PROFILE: IntelligenceProfile = {
  audience: 'all',
  municipalities: [],
  services: [],
  families: [],
}
const families = [
  'business_expansion',
  'land_assembly',
  'construction_timing',
  'infrastructure_unlock',
  'use_transition',
  'project_stall',
]
const services = [
  'equipment_rental',
  'sitework',
  'construction',
  'engineering',
  'surveying',
  'electrical',
  'mechanical',
  'specialty_installation',
  'brokerage',
]

function read(key: string): unknown {
  try {
    return JSON.parse(localStorage.getItem(workspaceStorageKey(key)) ?? 'null')
  } catch {
    return null
  }
}

function strings(value: unknown, limit: number, length: number): value is string[] {
  return (
    Array.isArray(value) &&
    value.length <= limit &&
    value.every(
      (item) => typeof item === 'string' && item.trim().length > 0 && item.length <= length,
    ) &&
    new Set(value).size === value.length
  )
}

export function isIntelligenceProfile(value: unknown): value is IntelligenceProfile {
  if (!value || typeof value !== 'object') {
    return false
  }
  const item = value as IntelligenceProfile
  return (
    ['all', 'investor', 'service_business'].includes(item.audience) &&
    strings(item.municipalities, 80, 100) &&
    strings(item.services, 20, 80) &&
    item.services.every((service) => services.includes(service)) &&
    strings(item.families, 6, 80) &&
    item.families.every((family) => families.includes(family)) &&
    (item.project_types === undefined ||
      (strings(item.project_types, 6, 40) &&
        item.project_types.every((type) =>
          [
            'industrial',
            'logistics',
            'housing',
            'mixed_use',
            'commercial',
            'infrastructure',
          ].includes(type),
        ))) &&
    (item.preferred_readiness === undefined ||
      (strings(item.preferred_readiness, 5, 20) &&
        item.preferred_readiness.every((stage) =>
          ['research', 'qualify', 'act', 'wait', 'closed'].includes(stage),
        )))
  )
}

export function isIntelligenceWork(value: unknown): value is IntelligenceWorkItem[] {
  return (
    Array.isArray(value) &&
    value.length <= 100 &&
    value.every(
      (item) =>
        item &&
        typeof item.case_key === 'string' &&
        /^emerging-[a-f0-9]{64}$/.test(item.case_key) &&
        ['saved', 'qualifying', 'waiting', 'acted', 'rejected'].includes(item.status) &&
        typeof item.note === 'string' &&
        item.note.length <= 4000 &&
        typeof item.last_seen_revision === 'string' &&
        /^[0-9]{1,20}$/.test(item.last_seen_revision) &&
        typeof item.updated_at === 'string' &&
        Number.isFinite(Date.parse(item.updated_at)),
    ) &&
    new Set(value.map((item) => item.case_key)).size === value.length
  )
}

export function getIntelligenceProfile(): IntelligenceProfile {
  const value = read(PROFILE_KEY)
  return isIntelligenceProfile(value) ? value : { ...DEFAULT_INTELLIGENCE_PROFILE }
}

export function getIntelligenceWork(): IntelligenceWorkItem[] {
  const value = read(WORK_KEY)
  return isIntelligenceWork(value) ? value : []
}

export function intelligenceStorageEntries(
  profile: IntelligenceProfile,
  work: IntelligenceWorkItem[],
) {
  return { [PROFILE_KEY]: JSON.stringify(profile), [WORK_KEY]: JSON.stringify(work) }
}
