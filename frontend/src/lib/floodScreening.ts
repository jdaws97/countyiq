import type { FloodZoneInfo, FloodZoneProperties } from '../types/api'
import { formatShortDate } from './format'

type FloodStatus = NonNullable<FloodZoneInfo['status']>

interface FloodScreeningPresentation {
  status: FloodStatus
  label: string
  detail: string
  summary: string
}

const STATUS_LABELS: Record<FloodStatus, string> = {
  overlap: 'Mapped SFHA overlap',
  no_overlap: 'No SFHA overlap in loaded mapping',
  unknown: 'Flood screening unknown',
}

export function presentFloodScreening(flood: FloodZoneInfo): FloodScreeningPresentation {
  // Older responses only establish an observed hit. False does not establish
  // whether FEMA mapping covers this parcel.
  const status = flood.status ?? (flood.in_flood_zone ? 'overlap' : 'unknown')
  const label = STATUS_LABELS[status]
  const details: string[] = []

  if (status === 'overlap') {
    if (flood.zone) {
      details.push(`Zone ${flood.zone}.`)
    }
    if (flood.overlap_pct != null && flood.overlap_pct > 0) {
      details.push(`${flood.overlap_pct.toFixed(1)}% of parcel area overlaps.`)
    }
  } else if (status === 'unknown') {
    details.push(
      flood.reason || 'Available mapping does not establish a result for the whole parcel.',
    )
  }

  if (flood.mapped_coverage_pct != null) {
    details.push(`${flood.mapped_coverage_pct.toFixed(1)}% mapped coverage.`)
  }

  const freshness = flood.freshness?.status ?? 'unknown'
  if (freshness === 'stale') {
    details.push('Loaded mapping is stale.')
  } else if (freshness === 'unknown') {
    details.push('Mapping freshness is unknown.')
  }

  const lastRun = formatShortDate(flood.freshness?.last_successful_run_at)
  if (lastRun) {
    details.push(`Last successful source run: ${lastRun}.`)
  }

  const detail = details.join(' ')
  return { status, label, detail, summary: `${label}.${detail ? ` ${detail}` : ''}` }
}

export function floodScreeningSummary(flood: FloodZoneInfo): string {
  return presentFloodScreening(flood).summary
}

export function floodLayerSfhaLabel(properties: FloodZoneProperties): string {
  const zone = properties.fld_zone?.trim().toUpperCase()
  const sfha = properties.sfha_tf?.trim().toUpperCase()
  if (zone === 'D') {
    return 'Unknown — undetermined flood hazard'
  }
  if (sfha === 'T') {
    return 'Yes'
  }
  if (sfha === 'F' && zone && ['B', 'C', 'X'].includes(zone)) {
    return 'No — mapped non-SFHA area'
  }
  return 'Unknown'
}
