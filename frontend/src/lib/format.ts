type CurrencyValue = number | string | null | undefined

function parseCurrencyValue(value: CurrencyValue): number | null {
  if (value == null || value === '') {
    return null
  }

  const parsed = typeof value === 'number' ? value : parseFloat(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function formatCurrency(value: CurrencyValue): string {
  const amount = parseCurrencyValue(value)
  if (amount == null) {
    return '--'
  }

  return `$${amount.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export function formatShortDate(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date)
}

export function formatLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

export function formatCurrencyCompact(
  value: CurrencyValue,
  options: { allowBillions?: boolean; allowThousands?: boolean } = {},
): string {
  const amount = parseCurrencyValue(value)
  if (amount == null || amount === 0) {
    return '--'
  }

  if (options.allowBillions && amount >= 1_000_000_000) {
    return `$${(amount / 1_000_000_000).toFixed(1)}B`
  }

  if (amount >= 1_000_000) {
    return `$${(amount / 1_000_000).toFixed(1)}M`
  }

  if (options.allowThousands && amount >= 1_000) {
    return `$${Math.round(amount / 1_000)}K`
  }

  return `$${amount.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}
