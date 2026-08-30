import { Link } from 'react-router-dom'
import Badge from './Badge'
import { formatLabel, formatShortDate } from '../lib/format'
import type { CountyNarrative } from '../types/api'

function narrativeTypeColor(type: string): string {
  if (type === 'corridor') return 'var(--accent-blue)'
  if (type === 'distress') return 'var(--accent-red)'
  if (type === 'municipal') return 'var(--accent-green)'
  if (type === 'portfolio') return 'var(--accent-gold)'
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
        {narrative.body}
      </div>

      {showAffectedPidns && pidnsToShow.length > 0 && (
        <div style={{ marginBottom: narrative.key_entities.length > 0 || narrative.citations.length > 0 ? 12 : 0 }}>
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
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
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
              <Badge key={entity} color="var(--accent-green)">{entity}</Badge>
            ))}
          </div>
        </div>
      )}

      {narrative.citations.length > 0 && (
        <div>
          <SectionLabel>Citations</SectionLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {narrative.citations.map((citation) => (
              <Badge key={citation} color="var(--accent-cyan)">{citation}</Badge>
            ))}
          </div>
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
