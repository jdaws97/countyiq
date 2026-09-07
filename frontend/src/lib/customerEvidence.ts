import type { EvidenceItem } from '../types/api'
import { formatCurrency, formatShortDate } from './format'

export interface SourceFact {
  label: string
  value: string
}

type FactFormat = 'text' | 'date' | 'money' | 'percent' | 'distance'

// Public investigation fields are explicit. New pipeline metadata must not
// become visible just because it was added to a stored source.
const FACT_FIELDS: Array<[string[], string, FactFormat]> = [
  [['address', 'propadr'], 'Address', 'text'],
  [['pidn'], 'Parcel number', 'text'],
  [['recorded_owner', 'owner_full'], 'Recorded owner', 'text'],
  [['previous_owner'], 'Previous recorded owner', 'text'],
  [['municipality', 'muni_name'], 'Municipality', 'text'],
  [['acres', 'total_acres'], 'Acres', 'text'],
  [['assessment', 'aprtotal'], 'Assessed value', 'money'],
  [['aprland'], 'Land assessment', 'money'],
  [['aprbldg'], 'Building assessment', 'money'],
  [['last_recorded_sale_date', 'saledt'], 'Recorded sale date', 'date'],
  [['last_recorded_sale_price', 'price'], 'Recorded sale consideration', 'money'],
  [['deed_bk'], 'Deed book', 'text'],
  [['deed_pg'], 'Deed page', 'text'],
  [['plan_title', 'project_name'], 'Plan', 'text'],
  [['sequence_number', 'plan_number', 'project_number'], 'Public plan number', 'text'],
  [['applicant', 'applicant_name'], 'Applicant', 'text'],
  [['engineer'], 'Engineer', 'text'],
  [['received_date'], 'Received', 'date'],
  [['proposed_lots'], 'Proposed lots', 'text'],
  [['proposed_dwelling_units'], 'Proposed homes', 'text'],
  [['proposed_new_building_sqft'], 'Proposed building area (sq ft)', 'text'],
  [['zname'], 'Mapped district', 'text'],
  [['zcode'], 'District code', 'text'],
  [['current_zoning'], 'Current zoning', 'text'],
  [['proposed_zoning'], 'Proposed zoning', 'text'],
  [['future_lu', 'future_land_use'], 'Future land-use policy', 'text'],
  [['ga_type'], 'Growth-area designation', 'text'],
  [['ga_status'], 'Growth-area status', 'text'],
  [['adopt_date', 'adpt_date'], 'Adopted', 'date'],
  [['site_name'], 'Site name', 'text'],
  [['facility_type'], 'Record type', 'text'],
  [['facility_status'], 'Recorded status', 'text'],
  [['distance_m'], 'Distance from property', 'distance'],
  [['mapped_coverage_pct', 'coverage_pct'], 'Mapped coverage', 'percent'],
  [['very_limited_septic_coverage_pct'], 'Soils rated very limited for septic', 'percent'],
  [['footprint_count'], 'Mapped building footprints', 'text'],
  [['zone', 'flood_zone'], 'Mapped flood zone', 'text'],
  [['association'], 'Relationship to this property', 'text'],
  [['meaning'], 'What this record establishes', 'text'],
]

function scalar(value: unknown): string | null {
  if (typeof value === 'string') {
    return value.trim() || null
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
  }
  return null
}

export function sourceFacts(item: EvidenceItem): SourceFact[] {
  const details = item.details ?? {}
  const facts: SourceFact[] = []
  if (item.source_kind === 'official_zoning_layer' || item.citation_key?.endsWith(':zoning')) {
    const district = scalar(details.name)
    const code = scalar(details.code)
    if (district) {
      facts.push({ label: 'Mapped zoning district', value: district })
    }
    if (code) {
      facts.push({ label: 'District code', value: code })
    }
  }
  for (const [keys, label, format] of FACT_FIELDS) {
    const key = keys.find((candidate) => scalar(details[candidate]) != null)
    if (!key) {
      continue
    }
    const raw = details[key]
    let value = scalar(raw)!
    if (format === 'date') {
      value = formatShortDate(value) ?? value
    } else if (format === 'money') {
      value = formatCurrency(raw as string | number)
    } else if (format === 'percent') {
      value = `${value}%`
    } else if (format === 'distance') {
      value = `${value} m`
    }
    facts.push({ label, value })
  }
  if (typeof details.delinquency_signal === 'boolean') {
    facts.push({
      label: 'Tax-claim listing',
      value: details.delinquency_signal
        ? 'Property appears in the listing'
        : 'No match in this listing',
    })
  }
  {
    const changes =
      details.changed && typeof details.changed === 'object'
        ? (details.changed as Record<string, unknown>)
        : details
    for (const [keys, label, format] of FACT_FIELDS) {
      const key = keys.find((candidate) => changes[candidate] != null)
      const change = key ? changes[key] : null
      if (!change || typeof change !== 'object') {
        continue
      }
      for (const side of ['old', 'new'] as const) {
        const value = scalar((change as Record<string, unknown>)[side])
        if (value == null) {
          continue
        }
        const display =
          format === 'money'
            ? formatCurrency((change as Record<string, unknown>)[side] as string | number)
            : format === 'date'
              ? (formatShortDate(value) ?? value)
              : value
        facts.push({
          label: `${label} · ${side === 'old' ? 'previous' : 'updated'}`,
          value: display,
        })
      }
    }
  }
  const units = details.map_units ?? details.units
  if (Array.isArray(units)) {
    for (const unit of units) {
      if (!unit || typeof unit !== 'object') {
        continue
      }
      const name = scalar(unit.map_unit_name ?? unit.name)
      if (!name) {
        continue
      }
      const coverage = scalar(unit.coverage_pct)
      const septic = scalar(unit.septic_rating)
      facts.push({
        label: 'Mapped soil',
        value: [name, coverage && `${coverage}% of property`, septic && `Septic rating: ${septic}`]
          .filter(Boolean)
          .join(' · '),
      })
    }
  }
  return facts
}

export function sourcePassages(item: EvidenceItem): Array<{ text: string; page: number | null }> {
  const passages = item.details?.passages
  if (Array.isArray(passages)) {
    const values = passages.flatMap((passage) => {
      if (!passage || typeof passage !== 'object' || typeof passage.text !== 'string') {
        return []
      }
      return [{ text: passage.text, page: typeof passage.page === 'number' ? passage.page : null }]
    })
    if (values.length > 0) {
      return values
    }
  }
  const page = item.details?.page_number ?? item.details?.page
  return item.excerpt ? [{ text: item.excerpt, page: typeof page === 'number' ? page : null }] : []
}

export function sourceTitle(item: EvidenceItem): string {
  const details = item.details ?? {}
  const specific = scalar(
    details.address ?? details.propadr ?? details.plan_title ?? details.site_name,
  )
  if (specific && !item.label.toLowerCase().includes(specific.toLowerCase())) {
    return `${specific} · ${item.label}`
  }
  return item.label
}

export function sourceDocumentLabel(item: EvidenceItem): string {
  const kind = item.details?.document_kind
  if (kind === 'agenda' || kind === 'minutes') {
    return kind === 'agenda' ? 'Meeting agenda' : 'Meeting minutes'
  }
  if (
    item.document_url ||
    item.source_kind.includes('municipal') ||
    item.source_kind.includes('proceeding')
  ) {
    return 'Source document'
  }
  return 'Public record'
}

export function sourceCaveat(item: EvidenceItem): string | null {
  const caveat = item.caveat ?? scalar(item.details?.caveat)
  if (
    !caveat ||
    /LLM interpretation is visibly separated|source facts, method|public product suppresses/i.test(
      caveat,
    )
  ) {
    return null
  }
  return caveat
}

export function sourcePropertyPath(item: EvidenceItem): string | null {
  const pidn = scalar(item.details?.pidn)
  if (pidn) {
    return `/property/${encodeURIComponent(pidn)}`
  }
  return item.internal_url?.startsWith('/') ? item.internal_url : null
}

export function sourceOriginalUrl(item: EvidenceItem): string | null {
  const url = item.document_url ?? item.url
  if (!url) {
    return null
  }
  const page = sourcePassages(item).find((passage) => passage.page != null)?.page
  return page != null && /\.pdf(?:[?#]|$)/i.test(url) ? `${url.split('#')[0]}#page=${page}` : url
}

export function citationKey(kind: string, value: string, group?: string): string {
  return (
    kind.toLowerCase() === 'evidence' ? `evidence:${group ?? ''}:${value}` : `${kind}:${value}`
  ).toLowerCase()
}

export const CITATION_PATTERN =
  /\[(Signal|Parcel):\s*([^\]]+)\]|\[Evidence:\s*([^:\]]+):([^\]]+)\]/gi
