import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Nav from '../components/Nav'

interface Project {
  project_id: string
  project_name: string
  description: string
  status: string
  start_date: string | null
  end_date: string | null
  cost: number | null
  project_type: string
  location_desc: string
  project_manager: string
  manager_email: string
  act89_status: string
  under_construction: string
}

const STATUS_ORDER: Record<string, number> = {
  Active: 0,
  Programmed: 1,
  Candidate: 2,
  Completed: 3,
}

const STATUS_STYLE: Record<
  string,
  { bg: string; border: string; text: string; accent: string }
> = {
  Active: {
    bg: 'rgba(61, 189, 111, 0.10)',
    border: 'rgba(61, 189, 111, 0.25)',
    text: 'var(--accent-green)',
    accent: '#3dbd6f',
  },
  Programmed: {
    bg: 'rgba(56, 189, 248, 0.10)',
    border: 'rgba(56, 189, 248, 0.25)',
    text: 'var(--accent-cyan)',
    accent: '#38bdf8',
  },
  Candidate: {
    bg: 'rgba(74, 127, 255, 0.10)',
    border: 'rgba(74, 127, 255, 0.25)',
    text: 'var(--accent-blue)',
    accent: '#4a7fff',
  },
  Completed: {
    bg: 'rgba(212, 168, 67, 0.10)',
    border: 'rgba(212, 168, 67, 0.25)',
    text: 'var(--accent-gold)',
    accent: '#d4a843',
  },
}

const DEFAULT_STYLE = {
  bg: 'rgba(123, 139, 178, 0.10)',
  border: 'rgba(123, 139, 178, 0.25)',
  text: 'var(--text-secondary)',
  accent: '#7b8bb2',
}

function getStatusStyle(status: string) {
  return STATUS_STYLE[status] ?? DEFAULT_STYLE
}

function formatCost(cost: number | null): string {
  if (cost == null) return '—'
  if (cost >= 1_000_000) return `$${(cost / 1_000_000).toFixed(1)}M`
  if (cost >= 1_000) return `$${Math.round(cost / 1_000)}K`
  return '$' + Math.round(cost).toLocaleString('en-US')
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

function sortProjects(projects: Project[]): Project[] {
  return [...projects].sort((a, b) => {
    const orderA = STATUS_ORDER[a.status] ?? 99
    const orderB = STATUS_ORDER[b.status] ?? 99
    if (orderA !== orderB) return orderA - orderB
    return a.project_name.localeCompare(b.project_name)
  })
}

export default function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/projects?limit=100')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: Project[]) => {
        setProjects(sortProjects(data))
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  const activeCount = projects.filter((p) => p.status === 'Active').length
  const totalCost = projects.reduce((sum, p) => sum + (p.cost ?? 0), 0)

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}>
      <Nav />

      <main style={{ maxWidth: 1200, margin: '0 auto', padding: '48px 32px' }}>
        {/* Page header */}
        <div style={{ marginBottom: 40, animation: 'fadeUp 0.4s ease both' }}>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: 3,
              textTransform: 'uppercase',
              color: 'var(--accent-gold)',
              marginBottom: 12,
            }}
          >
            Infrastructure
          </div>
          <h1
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 28,
              fontWeight: 600,
              letterSpacing: 1,
              textTransform: 'uppercase',
              color: 'var(--text-primary)',
              marginBottom: 8,
            }}
          >
            PennDOT Projects
          </h1>
          <p
            style={{
              fontFamily: 'var(--font-sans)',
              fontSize: 14,
              color: 'var(--text-secondary)',
            }}
          >
            Active transportation improvements in York County
          </p>
        </div>

        {/* Summary bar */}
        {!loading && !error && projects.length > 0 && (
          <div
            style={{
              display: 'flex',
              gap: 24,
              marginBottom: 36,
              flexWrap: 'wrap',
              animation: 'fadeUp 0.4s ease both',
              animationDelay: '0.05s',
              opacity: 0,
            }}
          >
            {[
              { label: 'Total Projects', value: projects.length.toString() },
              { label: 'Active', value: activeCount.toString(), accent: 'var(--accent-green)' },
              { label: 'Total Cost', value: formatCost(totalCost) },
            ].map(({ label, value, accent }) => (
              <div
                key={label}
                style={{
                  background: 'var(--bg-panel)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  padding: '14px 20px',
                  minWidth: 140,
                }}
              >
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    letterSpacing: 1.5,
                    textTransform: 'uppercase',
                    color: 'var(--text-muted)',
                    marginBottom: 6,
                  }}
                >
                  {label}
                </div>
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 22,
                    fontWeight: 600,
                    color: accent ?? 'var(--text-primary)',
                    letterSpacing: -0.5,
                  }}
                >
                  {value}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              color: 'var(--text-muted)',
              textAlign: 'center',
              padding: '80px 0',
            }}
          >
            Loading projects...
          </div>
        )}

        {/* Error state */}
        {error && (
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              color: 'var(--accent-red)',
              padding: '24px',
              background: 'rgba(224, 82, 82, 0.08)',
              border: '1px solid rgba(224, 82, 82, 0.2)',
              borderRadius: 6,
            }}
          >
            Failed to load projects: {error}
          </div>
        )}

        {/* Card grid */}
        {!loading && !error && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: 16,
            }}
          >
            {projects.map((project, idx) => {
              const style = getStatusStyle(project.status)
              return (
                <div
                  key={project.project_id}
                  style={{
                    background: 'var(--bg-panel)',
                    border: '1px solid var(--border)',
                    borderLeft: `3px solid ${style.accent}`,
                    borderRadius: 6,
                    padding: '20px 22px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 0,
                    animation: 'fadeUp 0.4s ease both',
                    animationDelay: `${0.08 + idx * 0.03}s`,
                    opacity: 0,
                    transition: 'background 0.15s ease',
                    cursor: 'default',
                  }}
                  onMouseEnter={(e) => {
                    ;(e.currentTarget as HTMLDivElement).style.background =
                      'var(--bg-card-hover)'
                  }}
                  onMouseLeave={(e) => {
                    ;(e.currentTarget as HTMLDivElement).style.background = 'var(--bg-panel)'
                  }}
                >
                  {/* Top row: name + badge */}
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: 12,
                      marginBottom: 8,
                    }}
                  >
                    <div
                      style={{
                        fontFamily: 'var(--font-sans)',
                        fontSize: 16,
                        fontWeight: 700,
                        color: 'var(--text-primary)',
                        lineHeight: 1.3,
                      }}
                    >
                      {project.project_name}
                    </div>

                    {/* Status badge */}
                    <span
                      style={{
                        flexShrink: 0,
                        fontFamily: 'var(--font-mono)',
                        fontSize: 10,
                        fontWeight: 600,
                        letterSpacing: 1.2,
                        textTransform: 'uppercase',
                        color: style.text,
                        background: style.bg,
                        border: `1px solid ${style.border}`,
                        borderRadius: 20,
                        padding: '3px 10px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {project.status}
                    </span>
                  </div>

                  {/* Location description */}
                  <div
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontSize: 13,
                      color: 'var(--text-secondary)',
                      lineHeight: 1.5,
                      marginBottom: 16,
                    }}
                  >
                    {project.location_desc || '—'}
                  </div>

                  {/* Stats row */}
                  <div
                    style={{
                      display: 'flex',
                      gap: 24,
                      marginBottom: 16,
                      flexWrap: 'wrap',
                    }}
                  >
                    <div>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 9,
                          letterSpacing: 1.5,
                          textTransform: 'uppercase',
                          color: 'var(--text-muted)',
                          marginBottom: 3,
                        }}
                      >
                        Cost
                      </div>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 14,
                          fontWeight: 600,
                          color: 'var(--text-primary)',
                        }}
                      >
                        {formatCost(project.cost)}
                      </div>
                    </div>

                    <div>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 9,
                          letterSpacing: 1.5,
                          textTransform: 'uppercase',
                          color: 'var(--text-muted)',
                          marginBottom: 3,
                        }}
                      >
                        Start
                      </div>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 14,
                          color: 'var(--text-secondary)',
                        }}
                      >
                        {formatDate(project.start_date)}
                      </div>
                    </div>

                    <div>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 9,
                          letterSpacing: 1.5,
                          textTransform: 'uppercase',
                          color: 'var(--text-muted)',
                          marginBottom: 3,
                        }}
                      >
                        End
                      </div>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 14,
                          color: 'var(--text-secondary)',
                        }}
                      >
                        {formatDate(project.end_date)}
                      </div>
                    </div>

                    {project.project_type && (
                      <div>
                        <div
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: 9,
                            letterSpacing: 1.5,
                            textTransform: 'uppercase',
                            color: 'var(--text-muted)',
                            marginBottom: 3,
                          }}
                        >
                          Type
                        </div>
                        <div
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: 13,
                            color: 'var(--text-muted)',
                            letterSpacing: 0.5,
                          }}
                        >
                          {project.project_type}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Divider */}
                  <div
                    style={{
                      height: 1,
                      background: 'var(--border)',
                      marginBottom: 14,
                    }}
                  />

                  {/* Project manager */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 8,
                      flexWrap: 'wrap',
                    }}
                  >
                    <div
                      style={{
                        fontFamily: 'var(--font-sans)',
                        fontSize: 13,
                        color: 'var(--text-secondary)',
                      }}
                    >
                      {project.project_manager || '—'}
                    </div>
                    {project.manager_email && (
                      <a
                        href={`mailto:${project.manager_email}`}
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 11,
                          color: 'var(--accent-blue)',
                          textDecoration: 'none',
                          letterSpacing: 0.2,
                        }}
                        onMouseEnter={(e) => {
                          ;(e.currentTarget as HTMLAnchorElement).style.textDecoration =
                            'underline'
                        }}
                        onMouseLeave={(e) => {
                          ;(e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none'
                        }}
                      >
                        {project.manager_email}
                      </a>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Back link */}
        <div
          style={{
            marginTop: 48,
            animation: 'fadeUp 0.4s ease both',
            animationDelay: '0.2s',
            opacity: 0,
          }}
        >
          <Link
            to="/"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              letterSpacing: 1,
              textTransform: 'uppercase',
              color: 'var(--text-muted)',
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              transition: 'color 0.15s ease',
            }}
            onMouseEnter={(e) => {
              ;(e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-secondary)'
            }}
            onMouseLeave={(e) => {
              ;(e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-muted)'
            }}
          >
            <span style={{ fontSize: 14 }}>&larr;</span> Back to Home
          </Link>
        </div>
      </main>
    </div>
  )
}
