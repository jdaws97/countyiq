import type { SiteInquiry, SiteIntakePacket } from '../types/siteIntake'
import { floodScreeningSummary } from './floodScreening'
import { SITE_QUESTION_KEYS } from './siteInquiries'

export interface HandoffSection {
  title: string
  paragraphs: string[]
}

export function handoffStageLabel(inquiry: SiteInquiry, packet: SiteIntakePacket): string {
  if (inquiry.status === 'ready_for_handoff' && inquiry.reviewed_revision !== packet.revision) {
    return 'Previously marked ready; current evidence needs review'
  }
  return inquiry.status.replaceAll('_', ' ')
}

export function collectionStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    ok: 'Collected',
    not_modified: 'Checked; no change',
    partial_error: 'Some records could not be collected',
    error: 'Collection needs attention',
    stale_or_unchecked: 'Collection needs a fresh check',
    robots_blocked: 'Collection unavailable',
  }
  return labels[status] ?? 'Collection status unverified'
}

export function siteReviewTopics(packet: SiteIntakePacket) {
  return (
    packet.review_topics ??
    packet.questions.map((question, index) => ({
      key: SITE_QUESTION_KEYS[index],
      question,
    }))
  )
}

export function sitePacketSections(
  inquiry: SiteInquiry,
  packet: SiteIntakePacket,
): HandoffSection[] {
  const report = packet.report
  const zoning = report.zoning
  const questions = siteReviewTopics(packet).map((topic) => {
    const review = inquiry.question_reviews?.find((item) => item.key === topic.key)
    const status =
      review?.status === 'answered'
        ? 'Answer recorded'
        : review?.status === 'not_applicable'
          ? 'Reviewer considers inapplicable'
          : 'Still open'
    return `${status}: ${topic.question}\n${review?.note || 'No reviewer response recorded.'}`
  })
  const municipal: string[] = []
  for (const card of report.municipal_evidence.cards) {
    municipal.push(
      `${card.title} | ${card.body_name} | ${card.meeting_date || 'Date unrecorded'} | ${card.proceeding_type}`,
      card.document_url,
    )
    if (card.proceeding_type === 'agenda') {
      municipal.push('Proposed business only; an agenda does not establish an outcome.')
    }
    if (!card.passages.length) {
      municipal.push('A reviewed English excerpt is not available. Consult the source document.')
    }
    for (const passage of card.passages) {
      municipal.push(`Page ${passage.page ?? 'unknown'}: ${passage.text}`)
    }
  }
  if (!report.municipal_evidence.cards.length) {
    municipal.push(
      'No linked passages in the loaded records. This does not establish that no applications or conditions exist.',
    )
  }
  if (report.municipal_evidence.more) {
    municipal.push(
      'Additional linked passages exist. Continue the property investigation before handoff.',
    )
  }
  const sources = report.evidence
    .flatMap((source) => [
      source.label,
      source.document_url || source.url || 'Original link unavailable',
      `Source-effective date: ${source.effective_at || 'unknown'}; added to CountyIQ: ${source.observed_at || 'unknown'}`,
      source.method || '',
      source.caveat || '',
    ])
    .filter(Boolean)

  return [
    { title: 'Proposed use — user input', paragraphs: [inquiry.proposed_use || 'Not supplied'] },
    {
      title: 'Site evidence',
      paragraphs: [
        `Mapped zoning at parcel center: ${zoning ? `${zoning.code} — ${zoning.name}` : 'Unknown'}. Confirm split zoning and the municipal ordinance.`,
        floodScreeningSummary(report.flood_zone),
        `Mapped soil coverage: ${report.soil_profile.mapped_coverage_pct}%. Missing mapping does not establish suitability.`,
        ...report.soil_profile.considerations,
      ],
    },
    { title: 'Questions & responses — user input', paragraphs: questions },
    {
      title: 'Additional open questions — user input',
      paragraphs: [inquiry.questions || 'No additional questions recorded.'],
    },
    { title: 'Reviewer notes — user input', paragraphs: [inquiry.note || 'None'] },
    { title: 'Site-linked municipal passages', paragraphs: municipal },
    {
      title: 'Source refreshes',
      paragraphs: [
        'These are acquisition dates, not map-effective dates. A recent refresh does not establish that a map or rule is current.',
        ...packet.sources.map(
          (source) =>
            `${source.label}: ${source.status}; last successful acquisition ${source.last_successful_run_at || 'unknown'}`,
        ),
      ],
    },
    {
      title: 'Municipal collection coverage',
      paragraphs: [
        ...packet.municipal_collection.map(
          (body) =>
            `${body.body_name}: ${collectionStatusLabel(body.status)}; last checked ${body.checked_at || 'unknown'}`,
        ),
        `Reviewed ${report.municipal_evidence.coverage.reviewed_documents} of ${report.municipal_evidence.coverage.total_documents} collected municipal records. Uncollected records are not counted.`,
      ],
    },
    { title: 'Source receipts', paragraphs: sources },
    { title: 'Scope of this handoff', paragraphs: [packet.scope_note] },
  ]
}

export function sitePacketText(inquiry: SiteInquiry, packet: SiteIntakePacket): string {
  const parcel = packet.report.parcel
  const reviewed = inquiry.reviewed_revision === packet.revision
  const lines = [
    'CountyIQ — Site inquiry research handoff',
    inquiry.label,
    `Prepared: ${new Date().toISOString()}`,
    `PIDN: ${inquiry.pidn} | Municipality: ${parcel.municipality || 'Unknown'}`,
    `Address: ${parcel.propadr || 'Not recorded'} | Recorded owner: ${parcel.owner_full || 'Unknown'}`,
    `Review: ${reviewed ? 'User reviewed this evidence revision' : 'DRAFT — evidence needs review'}`,
    `Workflow: ${handoffStageLabel(inquiry, packet)}`,
  ]
  for (const section of sitePacketSections(inquiry, packet)) {
    lines.push('', section.title.toUpperCase(), ...section.paragraphs)
  }
  return lines.join('\n')
}
