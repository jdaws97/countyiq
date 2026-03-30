import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Nav from '../components/Nav'
import SearchBar from '../components/SearchBar'
import StatCard from '../components/StatCard'

interface StatsData {
  total_records: number
  municipality_count: number
  delinquent_parcels: number
  total_delinquent: number
  flood_zone_count: number
  liquor_license_count: number
  address_point_count: number
  structure_count: number
  total_assessed: number
  county_tax_owed: number
  school_tax_owed: number
  municipal_tax_owed: number
  oldest_delinquent_year: number | null
  districts_affected: number
}

interface SourceInfo {
  status: string
  record_count: number
}

interface HealthData {
  overall: string
  sources: Record<string, SourceInfo>
  summary: string
}

/* Pretty names for source keys */
const SOURCE_DISPLAY: Record<string, string> = {
  structures: 'Building Structures',
  address_points: 'Address Points',
  pa_open_data: 'PA Businesses',
  tax_claims: 'Tax Claims',
  flood_zones: 'FEMA Flood Zones',
  plcb_licenses: 'PLCB Licenses',
  parcels: 'GIS Parcels',
  municipalities: 'Municipalities',
  roads: 'Roads',
  zoning: 'Zoning',
  penndot_roads: 'PennDOT Roads',
  penndot_projects: 'PennDOT Projects',
}

/* Active tiles config */
const ACTIVE_TILES = [
  { icon: '\u25CE', name: 'Explore Map', desc: 'Interactive map view', color: 'var(--accent-blue)', to: '/map' },
  { icon: '\u25C8', name: 'Flood Risk', desc: '', color: 'var(--accent-purple)', to: '/map?layer=flood' },
  { icon: '\u25C6', name: 'Delinquent Taxes', desc: '', color: 'var(--accent-red)', to: '/delinquent' },
  { icon: '\u25C7', name: 'Municipalities', desc: '', color: 'var(--accent-green)', to: '/municipalities' },
  { icon: '\u25A5', name: 'PennDOT Projects', desc: '', color: 'var(--accent-cyan)', to: '/projects' },
  { icon: '\u25A4', name: 'Recent Sales', desc: '', color: 'var(--accent-gold)', to: '/map' },
  { icon: '\u25A3', name: 'Liquor Licenses', desc: '', color: 'var(--accent-green)', to: '/licenses' },
  { icon: '\u25A2', name: 'Vacant Land', desc: '', color: 'var(--accent-purple)', to: '/map?layer=vacant' },
]

/* Disabled tiles config */
const DISABLED_TILES: { icon: string; name: string; desc: string }[] = []

function formatCurrency(value: number): string {
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`
  return `$${value.toLocaleString()}`
}

export default function HomePage() {
  const [stats, setStats] = useState<StatsData | null>(null)
  const [health, setHealth] = useState<HealthData | null>(null)

  useEffect(() => {
    fetch('/api/stats')
      .then((r) => r.json())
      .then(setStats)
      .catch(() => setStats(null))

    fetch('/api/ops/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  /* Derived values */
  const totalRecords = stats?.total_records ?? 0
  const delinquentParcels = stats?.delinquent_parcels ?? 0
  const totalDelinquent = stats?.total_delinquent ?? 0
  const municipalityCount = stats?.municipality_count ?? 0
  const floodZoneCount = stats?.flood_zone_count ?? 0
  const penndotProjectCount = health?.sources?.penndot_projects?.record_count ?? 0

  /* Source count for "across N data sources" */
  const greenSources = health
    ? Object.values(health.sources).filter((s) => s.status === 'green').length
    : 0
  const downSources = health
    ? Object.values(health.sources).filter((s) => s.status === 'red').length
    : 0

  const parcelCount = stats?.parcel_count ?? 0

  /* Dynamic tile descriptions */
  const activeTileDescs = [
    `${parcelCount.toLocaleString()} parcels`,
    `${floodZoneCount.toLocaleString()} FEMA zones`,
    `${delinquentParcels.toLocaleString()} parcels · ${formatCurrency(totalDelinquent)}`,
    `${municipalityCount} jurisdictions`,
    `${penndotProjectCount} active projects`,
    `${parcelCount.toLocaleString()} parcels tracked`,
    `${(stats?.liquor_license_count ?? 0).toLocaleString()} active licenses`,
    'Parcels without structures',
  ]
  const disabledTileDescs: string[] = [
    'Coming soon',
  ]

  /* Sort sources: green first, then red; by record count descending within each group */
  const sortedSources = health
    ? Object.entries(health.sources)
        .sort(([, a], [, b]) => {
          if (a.status !== b.status) return a.status === 'green' ? -1 : 1
          return b.record_count - a.record_count
        })
    : []

  return (
    <>
      <Nav />

      <main style={{ maxWidth: 1200, margin: '0 auto', padding: 32 }}>
        {/* Search */}
        <SearchBar />

        {/* Stats Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 16,
            marginBottom: 36,
            animation: 'fadeUp 0.6s ease-out 0.1s both',
          }}
        >
          <StatCard
            label="Parcels Tracked"
            value={parcelCount.toLocaleString()}
            detail={`across ${greenSources} data sources`}
            color="var(--accent-blue)"
          />
          <StatCard
            label="Tax Delinquent"
            value={delinquentParcels.toLocaleString()}
            detail={`${formatCurrency(totalDelinquent)} outstanding`}
            color="var(--accent-gold)"
          />
          <StatCard
            label="Total Assessed"
            value={formatCurrency(stats?.total_assessed ?? 0)}
            detail={`${municipalityCount} municipalities`}
            color="var(--accent-green)"
          />
        </div>

        {/* Quick Access */}
        <SectionHeader title="Quick Access" />
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 12,
            marginBottom: 36,
            animation: 'fadeUp 0.6s ease-out 0.2s both',
          }}
        >
          {ACTIVE_TILES.map((tile, i) => (
            <Link
              key={tile.name}
              to={tile.to}
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <Tile
                icon={tile.icon}
                name={tile.name}
                desc={activeTileDescs[i]}
                accentColor={tile.color}
                active
              />
            </Link>
          ))}
          {DISABLED_TILES.map((tile, i) => (
            <Tile
              key={tile.name}
              icon={tile.icon}
              name={tile.name}
              desc={disabledTileDescs[i]}
              disabled
            />
          ))}
        </div>

        {/* Intelligence Briefing */}
        <SectionHeader title="Intelligence Briefing" />
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 16,
            animation: 'fadeUp 0.6s ease-out 0.3s both',
          }}
        >
          {/* Tax Delinquency Panel */}
          <IntelPanel
            title="Tax Delinquency"
            badge="Report: Mar 27"
            badgeVariant="live"
          >
            <IntelRow label="Delinquent parcels" value={delinquentParcels.toLocaleString()} valueClass="gold" />
            <IntelRow label="Total outstanding" value={formatCurrency(totalDelinquent)} valueClass="red" />
            <IntelRow label="County tax owed" value={stats?.county_tax_owed ? formatCurrency(stats.county_tax_owed) : '--'} valueClass="default" />
            <IntelRow label="School tax owed" value={stats?.school_tax_owed ? formatCurrency(stats.school_tax_owed) : '--'} valueClass="default" />
            <IntelRow label="Municipal tax owed" value={stats?.municipal_tax_owed ? formatCurrency(stats.municipal_tax_owed) : '--'} valueClass="default" />
            <IntelRow label="Oldest delinquency" value={stats?.oldest_delinquent_year?.toString() ?? '--'} valueClass="gold" />
            <IntelRow label="Districts affected" value={stats?.districts_affected?.toString() ?? '--'} valueClass="default" />
          </IntelPanel>

          {/* Data Sources Panel */}
          <IntelPanel
            title="Data Sources"
            badge={downSources > 0 ? `${downSources} down` : 'All green'}
            badgeVariant={downSources > 0 ? 'warn' : 'live'}
          >
            {sortedSources.map(([key, src]) => (
              <SourceRow
                key={key}
                name={SOURCE_DISPLAY[key] ?? key}
                status={src.status}
                count={src.record_count}
              />
            ))}
          </IntelPanel>
        </div>
      </main>

      {/* Footer */}
      <footer
        style={{
          maxWidth: 1200,
          margin: '32px auto 0',
          padding: '20px 32px',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--text-muted)',
          letterSpacing: 0.5,
        }}
      >
        <span>CountyIQ &middot; York County Civic Intelligence Platform</span>
        <span>Data sources updated weekly &middot; Not for legal reliance</span>
      </footer>
    </>
  )
}

/* ─── Sub-components ─── */

function SectionHeader({ title }: { title: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
      <h2
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          textTransform: 'uppercase',
          letterSpacing: 2.5,
          color: 'var(--text-muted)',
          fontWeight: 500,
        }}
      >
        {title}
      </h2>
      <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
    </div>
  )
}

function Tile({
  icon,
  name,
  desc,
  accentColor,
  active,
  disabled,
}: {
  icon: string
  name: string
  desc: string
  accentColor?: string
  active?: boolean
  disabled?: boolean
}) {
  const [hovered, setHovered] = useState(false)

  return (
    <div
      onMouseEnter={() => !disabled && setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered ? 'var(--bg-card-hover)' : 'var(--bg-panel)',
        border: `1px solid ${hovered && active ? 'var(--accent-blue)' : active ? 'var(--border-active)' : 'var(--border)'}`,
        borderRadius: 6,
        padding: '20px 16px',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'all 0.2s',
        position: 'relative',
        overflow: 'hidden',
        opacity: disabled ? 0.3 : 1,
        pointerEvents: disabled ? 'none' : 'auto',
        transform: hovered ? 'translateY(-1px)' : 'none',
      }}
    >
      {accentColor && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: 3,
            height: '100%',
            background: accentColor,
          }}
        />
      )}
      <span style={{ fontSize: 22, marginBottom: 10, display: 'block' }}>{icon}</span>
      <div
        style={{
          fontFamily: 'var(--font-sans)',
          fontWeight: 600,
          fontSize: 13,
          color: 'var(--text-primary)',
          marginBottom: 4,
        }}
      >
        {name}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--text-muted)',
          letterSpacing: 0.3,
        }}
      >
        {desc}
      </div>
    </div>
  )
}

function IntelPanel({
  title,
  badge,
  badgeVariant,
  children,
}: {
  title: string
  badge: string
  badgeVariant: 'live' | 'warn'
  children: React.ReactNode
}) {
  const badgeStyle =
    badgeVariant === 'live'
      ? {
          background: 'rgba(61, 189, 111, 0.15)',
          color: 'var(--accent-green)',
          border: '1px solid rgba(61, 189, 111, 0.3)',
        }
      : {
          background: 'rgba(212, 168, 67, 0.15)',
          color: 'var(--accent-gold)',
          border: '1px solid rgba(212, 168, 67, 0.3)',
        }

  return (
    <div
      style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 20px',
          borderBottom: '1px solid var(--border)',
          background: 'rgba(20, 26, 46, 0.5)',
        }}
      >
        <h3
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            textTransform: 'uppercase',
            letterSpacing: 2,
            color: 'var(--text-secondary)',
            fontWeight: 500,
          }}
        >
          {title}
        </h3>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            padding: '2px 8px',
            borderRadius: 3,
            letterSpacing: 0.5,
            ...badgeStyle,
          }}
        >
          {badge}
        </span>
      </div>
      <div style={{ padding: '16px 20px' }}>{children}</div>
    </div>
  )
}

const VALUE_COLORS: Record<string, string> = {
  red: 'var(--accent-red)',
  gold: 'var(--accent-gold)',
  green: 'var(--accent-green)',
  blue: 'var(--accent-blue)',
  default: 'var(--text-primary)',
}

function IntelRow({
  label,
  value,
  valueClass,
  isLast,
}: {
  label: string
  value: string
  valueClass: string
  isLast?: boolean
}) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        padding: '10px 0',
        borderBottom: isLast ? 'none' : '1px solid rgba(30, 40, 68, 0.6)',
      }}
    >
      <span style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-secondary)' }}>
        {label}
      </span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 14,
          fontWeight: 600,
          color: VALUE_COLORS[valueClass] ?? VALUE_COLORS.default,
        }}
      >
        {value}
      </span>
    </div>
  )
}

function SourceRow({ name, status, count }: { name: string; status: string; count: number }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 0',
        borderBottom: '1px solid rgba(30, 40, 68, 0.6)',
        fontSize: 12,
      }}
    >
      <div
        style={{
          width: 5,
          height: 5,
          borderRadius: '50%',
          flexShrink: 0,
          background: status === 'green' ? 'var(--accent-green)' : 'var(--accent-red)',
          boxShadow:
            status === 'green'
              ? '0 0 4px rgba(61,189,111,0.4)'
              : '0 0 4px rgba(224,82,82,0.4)',
        }}
      />
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          color: 'var(--text-secondary)',
          flex: 1,
          fontSize: 11,
        }}
      >
        {name}
      </span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          color: status === 'green' ? 'var(--text-muted)' : 'var(--accent-red)',
          fontSize: 11,
        }}
      >
        {status === 'green' ? count.toLocaleString() : 'offline'}
      </span>
    </div>
  )
}
