import { Link } from 'react-router-dom'
import Badge from './Badge'
import EvidencePanel, { CitedText } from './EvidencePanel'
import { useSourceViewer } from '../lib/useSourceViewer'
import { formatLabel, formatShortDate } from '../lib/format'
import type { CountyNarrative } from '../types/api'

function narrativeTypeColor(type: string): string {
  if (type === 'corridor') {
    return 'var(--accent-blue)'
  }
  if (type === 'distress') {
    return 'var(--accent-red)'
  }
  if (type === 'municipal') {
    return 'var(--accent-green)'
  }
  if (type === 'portfolio') {
    return 'var(--accent-gold)'
  }
  return 'var(--accent-cyan)'
}

type NarrativeWithPidns = CountyNarrative & { affected_pidns?: string[] }

export default function NarrativeCard({
  narrative,
  showAffectedPidns = false,
  titleAs = 'h3',
}: {
  narrative: NarrativeWithPidns
  showAffectedPidns?: boolean
  titleAs?: 'h2' | 'h3'
}) {
  const openSource = useSourceViewer()
  const affected = narrative.affected_pidns ?? []
  const pidnsToShow = affected.slice(0, 10)
  const extraPidns = affected.length - pidnsToShow.length
  const TitleTag = titleAs

  return (
    <article
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: 20,
      }}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
        <Badge color={narrativeTypeColor(narrative.narrative_type)}>
          {formatLabel(narrative.narrative_type)}
        </Badge>
        {narrative.trajectory && (
          <Badge color="var(--accent-gold)">{formatLabel(narrative.trajectory)}</Badge>
        )}
        {narrative.generated_at && (
          <Badge color="var(--accent-cyan)">{formatShortDate(narrative.generated_at)}</Badge>
        )}
      </div>

      <TitleTag
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: 20,
          fontWeight: 600,
          color: 'var(--text-primary)',
          marginBottom: 10,
        }}
      >
        {narrative.title}
      </TitleTag>

      <div
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: 14,
          lineHeight: 1.7,
          color: 'var(--text-secondary)',
          marginBottom: 16,
        }}
      >
        <CitedText text={narrative.body} evidence={narrative.citation_evidence ?? []} />
      </div>

      {showAffectedPidns && pidnsToShow.length > 0 && (
        <div
          style={{
            marginBottom:
              narrative.key_entities.length > 0 || narrative.citations.length > 0 ? 12 : 0,
          }}
        >
          <SectionLabel>Affected Parcels</SectionLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {pidnsToShow.map((pidn) => (
              <Link
                key={pidn}
                to={`/property/${pidn}`}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--accent-blue)',
                  textDecoration: 'none',
                  padding: '2px 8px',
                  border: '1px solid var(--border)',
                  borderRadius: 3,
                }}
              >
                {pidn}
              </Link>
            ))}
            {extraPidns > 0 && (
              <span
                style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}
              >
                +{extraPidns} more
              </span>
            )}
          </div>
        </div>
      )}

      {narrative.key_entities.length > 0 && (
        <div style={{ marginBottom: narrative.citations.length > 0 ? 12 : 0 }}>
          <SectionLabel>Key Entities</SectionLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {narrative.key_entities.map((entity) => (
              <Badge key={entity} color="var(--accent-green)">
                {entity}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {narrative.citations.length > 0 && (
        <div>
          <SectionLabel>Citations</SectionLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {narrative.citations.map((citation) => {
              const index = (narrative.citation_evidence ?? []).findIndex(
                (item) => item.citation_key.toLowerCase() === `signal:${citation}`.toLowerCase(),
              )
              const receipt = index >= 0 ? narrative.citation_evidence[index] : null
              return receipt ? (
                <a
                  key={citation}
                  href={`#${receipt.evidence_id}`}
                  onClick={(event) => {
                    event.preventDefault()
                    openSource(narrative.citation_evidence, index)
                  }}
                  style={{ textDecoration: 'none' }}
                >
                  <Badge color="var(--accent-cyan)">
                    E{index + 1} · {formatLabel(citation)}
                  </Badge>
                </a>
              ) : (
                <Badge key={citation} color="var(--text-muted)">
                  {formatLabel(citation)}
                </Badge>
              )
            })}
          </div>
        </div>
      )}
      {(narrative.citation_evidence?.length ?? 0) > 0 && (
        <div style={{ marginTop: 14 }}>
          <EvidencePanel items={narrative.citation_evidence} title="Verify this narrative" />
        </div>
      )}
    </article>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        letterSpacing: 1.5,
        textTransform: 'uppercase',
        color: 'var(--text-muted)',
        marginBottom: 6,
      }}
    >
      {children}
    </div>
  )
}
