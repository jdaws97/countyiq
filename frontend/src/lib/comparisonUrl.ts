const MAX_COMPARISON_PARCELS = 4
const MIN_COMPARISON_PARCELS = 2
const PIDN_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$/

export type ComparisonUrlSelection =
  { status: 'absent' | 'invalid'; pidns: [] } | { status: 'selection'; pidns: string[] }

export function comparisonUrlSelection(search: string): ComparisonUrlSelection {
  const params = new URLSearchParams(search)
  const values = params.getAll('pidn')
  const mode = params.getAll('compare')
  const pidns = [...new Set(values)]

  if (values.length === 0 && mode.length === 0) {
    return { status: 'absent', pidns: [] }
  }

  const editing = mode.length === 1 && mode[0] === 'editing'
  const shared = mode.length === 0 && pidns.length >= MIN_COMPARISON_PARCELS
  if (
    values.length !== pidns.length ||
    pidns.length > MAX_COMPARISON_PARCELS ||
    !pidns.every((pidn) => PIDN_PATTERN.test(pidn)) ||
    (!editing && !shared) ||
    (editing && pidns.length > 1)
  ) {
    return { status: 'invalid', pidns: [] }
  }

  return { status: 'selection', pidns }
}

export function comparisonPidns(search: string): string[] | null {
  const selection = comparisonUrlSelection(search)
  if (selection.status !== 'selection' || selection.pidns.length < MIN_COMPARISON_PARCELS) {
    return null
  }
  return selection.pidns
}

export function comparisonUrl(pidns: string[], currentUrl: string): string | null {
  const validated = comparisonPidns(
    pidns.map((pidn) => `pidn=${encodeURIComponent(pidn)}`).join('&'),
  )
  if (!validated) {
    return null
  }

  const url = new URL(currentUrl)
  url.pathname = '/compare'
  url.search = new URLSearchParams(validated.map((pidn) => ['pidn', pidn])).toString()
  url.hash = ''
  return url.toString()
}

export function comparisonEditingUrl(pidns: string[], currentUrl: string): string | null {
  if (pidns.length > 1 || !pidns.every((pidn) => PIDN_PATTERN.test(pidn))) {
    return null
  }

  const url = new URL(currentUrl)
  url.pathname = '/compare'
  const params = new URLSearchParams([['compare', 'editing']])
  for (const pidn of pidns) {
    params.append('pidn', pidn)
  }
  url.search = params.toString()
  url.hash = ''
  return url.toString()
}
