import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import PageShell from '../components/PageShell'
import ReportActions from '../components/ReportActions'
import { Button, ButtonLink, EmptyState, PageHeader, StatusMessage } from '../components/ui'
import { formatCurrency } from '../lib/format'
import { clearComparison, downloadText, getComparison, toCsv, toggleComparison } from '../lib/investigationState'
import { getPropertyClassLabel } from '../lib/propertyLabels'
import type { PropertyReport } from '../types/api'

export default function ParcelCompare() {
  const [pidns, setPidns] = useState<string[]>(() => getComparison())
  const [reports, setReports] = useState<PropertyReport[]>([])
  const [resolvedKey, setResolvedKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const requestKey = pidns.join('|')
  const loading = pidns.length > 0 && resolvedKey !== requestKey
  const activeReports = reports.filter((report) => pidns.includes(report.parcel.pidn))

  useEffect(() => {
    const refresh = () => setPidns(getComparison())
    window.addEventListener('countyiq-investigation-changed', refresh)
    return () => window.removeEventListener('countyiq-investigation-changed', refresh)
  }, [])

  useEffect(() => {
    if (pidns.length === 0) {
      return
    }
    let cancelled = false
    const key = pidns.join('|')
    Promise.allSettled(pidns.map(async (pidn) => {
      const response = await fetch(`/api/parcels/${encodeURIComponent(pidn)}`)
      if (!response.ok) throw new Error(`Could not load parcel ${pidn}`)
      return response.json() as Promise<PropertyReport>
    }))
      .then((results) => {
        if (!cancelled) {
          const values = results.flatMap((result) => result.status === 'fulfilled' ? [result.value] : [])
          const failed = results.flatMap((result, index) => result.status === 'rejected' ? [pidns[index]] : [])
          setReports(values)
          setError(failed.length > 0
            ? `Could not load ${failed.length} parcel${failed.length === 1 ? '' : 's'}: ${failed.join(', ')}. Available parcels are shown below.`
            : null)
          setResolvedKey(key)
        }
      })
    return () => { cancelled = true }
  }, [pidns])

  const exportCsv = () => {
    const rows: Array<Array<string | number | boolean | null>> = [[
      'PIDN', 'Address', 'Owner', 'Municipality', 'Class', 'Acres', 'Assessed total',
      'Last sale date', 'Last sale price', 'Tax delinquency signal', 'Flood zone',
      'Structures', 'Evidence receipts',
    ]]
    for (const report of activeReports) {
      const p = report.parcel
      rows.push([
        p.pidn, p.propadr, p.owner_full, p.municipality, getPropertyClassLabel(p.class),
        p.acres == null ? null : Number(p.acres), p.aprtotal, p.saledt, p.price,
        report.tax_delinquency.is_delinquent, report.flood_zone.in_flood_zone
          ? report.flood_zone.zone ?? 'yes'
          : 'no',
        report.structures.count, report.evidence.length,
      ])
    }
    downloadText(`countyiq-parcel-comparison-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(rows), 'text/csv')
  }

  return (
    <PageShell maxWidth={1180}>
      <PageHeader
        eyebrow="Site diligence workspace"
        title="Parcel Comparison"
        description="Compare two to four property records side by side. Scores are screening aids; open each case file to inspect its source receipts."
        actions={activeReports.length > 0 ? (
          <>
            <Button tone="quiet" onClick={exportCsv}>Export CSV</Button>
            <ReportActions label="CountyIQ parcel comparison" />
            <Button tone="danger" onClick={clearComparison}>Clear</Button>
          </>
        ) : undefined}
      />

      {pidns.length < 2 && (
        <div className="comparison-notice">
          Select {pidns.length === 0 ? 'at least two parcels' : 'one more parcel'} to build a useful comparison.
          <ButtonLink to="/radar" tone="secondary">Browse Radar</ButtonLink>
        </div>
      )}

      {loading && <StatusMessage>Loading property records…</StatusMessage>}
      {error && <StatusMessage tone="error">{error}</StatusMessage>}

      {!loading && !error && activeReports.length === 0 && (
        <EmptyState
          title="No parcels selected"
          actions={<><ButtonLink to="/radar" tone="primary">Explore Radar</ButtonLink><ButtonLink to="/map">Open map</ButtonLink></>}
        >
          Add parcels from a property report or Development Radar. Your comparison stays in this browser until you clear it.
        </EmptyState>
      )}

      {!loading && activeReports.length > 0 && (
        <div className="comparison-table" role="table" aria-label="Parcel comparison">
          <ComparisonRow label="Property" reports={activeReports} render={(report) => (
            <div className="comparison-property">
              <Link to={`/property/${report.parcel.pidn}`}>{report.parcel.propadr || report.parcel.pidn}</Link>
              <span>{report.parcel.owner_full || 'Owner not displayed'}</span>
              <Button tone="quiet" onClick={() => toggleComparison(report.parcel.pidn)}>Remove</Button>
            </div>
          )} />
          <ComparisonRow label="Municipality" reports={activeReports} render={(report) => report.parcel.municipality || '—'} />
          <ComparisonRow label="Property class" reports={activeReports} render={(report) => getPropertyClassLabel(report.parcel.class) || '—'} />
          <ComparisonRow label="Acres" reports={activeReports} render={(report) => report.parcel.acres == null ? '—' : Number(report.parcel.acres).toFixed(2)} />
          <ComparisonRow label="Assessed total" reports={activeReports} render={(report) => formatCurrency(report.parcel.aprtotal)} emphasize />
          <ComparisonRow label="Last sale" reports={activeReports} render={(report) => `${formatCurrency(report.parcel.price)}${report.parcel.saledt ? ` · ${report.parcel.saledt}` : ''}`} />
          <ComparisonRow label="Tax status" reports={activeReports} render={(report) => report.tax_delinquency.is_delinquent ? 'Delinquency signal' : 'No signal'} />
          <ComparisonRow label="Flood screening" reports={activeReports} render={(report) => report.flood_zone.in_flood_zone ? `Zone ${report.flood_zone.zone || '—'}` : 'Not in mapped flood zone'} />
          <ComparisonRow label="Structures" reports={activeReports} render={(report) => `${report.structures.count}${report.structures.likely_vacant ? ' · likely vacant' : ''}`} />
          <ComparisonRow label="Evidence" reports={activeReports} render={(report) => `${report.evidence.length} receipt${report.evidence.length === 1 ? '' : 's'}`} />
        </div>
      )}
    </PageShell>
  )
}

function ComparisonRow({
  label,
  reports,
  render,
  emphasize = false,
}: {
  label: string
  reports: PropertyReport[]
  render: (report: PropertyReport) => React.ReactNode
  emphasize?: boolean
}) {
  return (
    <div className={`comparison-row${emphasize ? ' comparison-row-emphasize' : ''}`} role="row">
      <div className="comparison-label" role="rowheader">{label}</div>
      {reports.map((report) => <div key={report.parcel.pidn} className="comparison-cell" role="cell">{render(report)}</div>)}
    </div>
  )
}
