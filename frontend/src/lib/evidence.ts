export function openEvidenceReceipt(evidenceId: string) {
  const receipt = document.getElementById(evidenceId)
  if (receipt instanceof HTMLDetailsElement) receipt.open = true
}

/**
 * Name an outbound evidence link by what the reader will land on. A bare
 * ArcGIS layer endpoint is the layer's REST index, not a record; the API
 * deep-links records where it can, and the label is honest when it cannot.
 */
export function sourceLinkLabel(href: string): string {
  if (/\.pdf(\?|#|$)/i.test(href)) return 'Open original document ↗'
  if (/\/rest\/services\//i.test(href)) {
    return /\/query\?/i.test(href) ? 'Open official GIS record ↗' : 'Open source GIS layer ↗'
  }
  return 'Open original source ↗'
}
