interface StatCardProps {
  label: string
  value: string | number
  detail: string
  color: string
}

export default function StatCard({ label, value, detail, color }: StatCardProps) {
  return (
    <div
      style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '20px 24px',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Top accent bar */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 2,
          background: color,
        }}
      />
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          textTransform: 'uppercase',
          letterSpacing: 2,
          color: 'var(--text-muted)',
          marginBottom: 8,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 32,
          fontWeight: 700,
          letterSpacing: -1,
          lineHeight: 1,
          color,
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--text-secondary)',
          marginTop: 6,
        }}
      >
        {detail}
      </div>
    </div>
  )
}
