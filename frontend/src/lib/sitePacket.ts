import type { SiteInquiry, SiteIntakePacket } from '../types/siteIntake'
import { floodScreeningSummary } from './floodScreening'

export function sitePacketText(inquiry: SiteInquiry, packet: SiteIntakePacket): string {
  const report = packet.report
  const parcel = report.parcel
  const zoning = report.zoning
  const reviewed = inquiry.reviewed_revision === packet.revision
  const lines = [
    'CountyIQ — Site inquiry research handoff',
    inquiry.label,
    `Prepared: ${new Date().toISOString()}`,
    `PIDN: ${inquiry.pidn} | Municipality: ${parcel.municipality || 'Unknown'}`,
    `Address: ${parcel.propadr || 'Not recorded'} | Recorded owner: ${parcel.owner_full || 'Unknown'}`,
    `Review: ${reviewed ? 'User reviewed this evidence revision' : 'Evidence needs review'}`,
    `Workflow: ${inquiry.status.replaceAll('_', ' ')}`,
    '',
    'PROPOSED USE — USER INPUT',
    inquiry.proposed_use || 'Not supplied',
    '',
    'SITE EVIDENCE',
    `Mapped zoning at parcel center: ${zoning ? `${zoning.code} — ${zoning.name}` : 'Unknown'}. Confirm split zoning and the municipal ordinance.`,
    floodScreeningSummary(report.flood_zone),
    `Mapped soil coverage: ${report.soil_profile.mapped_coverage_pct}%. Missing mapping does not establish suitability.`,
    ...report.soil_profile.considerations,
    '',
    'SOURCE REFRESHES — NOT MAP-EFFECTIVE DATES',
    ...packet.sources.map(
      (source) =>
        `${source.label}: ${source.status}; last successful acquisition ${source.last_successful_run_at || 'unknown'}`,
    ),
    '',
    'MUNICIPAL COLLECTION COVERAGE',
    ...packet.municipal_collection.map(
      (body) => `${body.body_name}: ${body.status}; last checked ${body.checked_at || 'unknown'}`,
    ),
    `Reviewed ${report.municipal_evidence.coverage.reviewed_documents} of ${report.municipal_evidence.coverage.total_documents} collected municipal records. Uncollected records are not counted.`,
    '',
    'SITE-LINKED MUNICIPAL PASSAGES',
  ]
  for (const card of report.municipal_evidence.cards) {
    lines.push(
      `${card.title} | ${card.body_name} | ${card.meeting_date} | ${card.proceeding_type}`,
      card.document_url,
    )
    if (card.proceeding_type === 'agenda') {
      lines.push('Proposed business only; an agenda does not establish an outcome.')
    }
    if (!card.passages.length) {
      lines.push('A reviewed English excerpt is not available. Consult the source document.')
    }
    for (const passage of card.passages) {
      lines.push(`Page ${passage.page ?? 'unknown'}: ${passage.text}`)
    }
  }
  if (!report.municipal_evidence.cards.length) {
    lines.push(
      'No linked passages in the loaded records. This does not establish that no applications or conditions exist.',
    )
  }
  if (report.municipal_evidence.more) {
    lines.push(
      'Additional linked passages exist. Continue the property investigation before handoff.',
    )
  }
  lines.push(
    '',
    'VERIFICATION CHECKLIST',
    ...packet.questions,
    '',
    'OPEN QUESTIONS — USER INPUT',
    inquiry.questions || 'No user-entered questions; review the checklist above.',
    '',
    'REVIEWER NOTES — USER INPUT',
    inquiry.note || 'None',
    '',
    'SOURCE RECEIPTS',
  )
  for (const source of report.evidence) {
    lines.push(
      source.label,
      source.document_url || source.url || 'Original link unavailable',
      `Source-effective date: ${source.effective_at || 'unknown'}; added to CountyIQ: ${source.observed_at || 'unknown'}`,
      source.method || '',
      source.caveat || '',
    )
  }
  lines.push('', packet.scope_note, `Evidence revision: ${packet.revision}`)
  return lines.join('\n')
}
