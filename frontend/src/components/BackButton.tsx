export default function BackButton({
  onClick,
  marginBottom = 24,
}: {
  onClick: () => void
  marginBottom?: number
}) {
  return (
    <button
      onClick={onClick}
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--text-muted)',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        padding: 0,
        marginBottom,
      }}
    >
      &larr; Back
    </button>
  )
}
