import ParcelContextMap from '../ParcelContextMap'
import { SITE_STAGE_LABELS } from '../../lib/siteInquiries'
import type { SiteInquiry, SiteIntakePacket } from '../../types/siteIntake'

type InquiryProposalProps = {
  draft: SiteInquiry
  packet: SiteIntakePacket | null
  reviewed: boolean
  onChange: (change: Partial<SiteInquiry>) => void
}

export default function InquiryProposal({
  draft,
  packet,
  reviewed,
  onChange,
}: InquiryProposalProps) {
  const parcel = packet?.report.parcel
  return (
    <div className="site-brief-layout">
      <aside className="site-property-context" aria-labelledby="site-identity-heading">
        <div className="page-eyebrow">Candidate property</div>
        <h2 id="site-identity-heading">{parcel?.propadr || `Parcel ${draft.pidn}`}</h2>
        {parcel && (
          <p>
            {parcel.municipality || 'Municipality unknown'} · {parcel.acres ?? 'Unknown'} acres
          </p>
        )}
        {packet && <ParcelContextMap report={packet.report} />}
        <dl className="site-identity-details">
          <div>
            <dt>Parcel ID</dt>
            <dd>{draft.pidn}</dd>
          </div>
          <div>
            <dt>Recorded owner</dt>
            <dd>{parcel?.owner_full || 'Current record unavailable'}</dd>
          </div>
        </dl>
        <p className="site-muted">
          Confirm the boundary and reviewing authority before using the handoff.
        </p>
      </aside>
      <section
        id="site-proposal"
        className="site-proposal site-section"
        aria-labelledby="inquiry-input-heading"
      >
        <div className="page-eyebrow">01 · Frame the inquiry</div>
        <h2 id="inquiry-input-heading">What is the client considering?</h2>
        <p className="site-muted">Your private working brief. Source evidence stays separate.</p>
        <div className="site-form-grid">
          <label className="site-full">
            Inquiry name
            <input
              value={draft.label}
              placeholder={parcel?.propadr || `Parcel ${draft.pidn}`}
              onChange={(event) => onChange({ label: event.target.value })}
              maxLength={200}
            />
          </label>
          <label className="site-full">
            Proposed use
            <textarea
              value={draft.proposed_use}
              onChange={(event) =>
                onChange({
                  proposed_use: event.target.value,
                  reviewed_revision: null,
                  status: draft.status === 'ready_for_handoff' ? 'researching' : draft.status,
                })
              }
              maxLength={2000}
              rows={4}
              placeholder="Describe the intended use, scale and current stage."
            />
          </label>
          <label className="site-full">
            Workflow stage
            <select
              value={draft.status}
              onChange={(event) =>
                onChange({ status: event.target.value as SiteInquiry['status'] })
              }
            >
              {Object.entries(SITE_STAGE_LABELS).map(([value, label]) => (
                <option
                  key={value}
                  value={value}
                  disabled={value === 'ready_for_handoff' && !reviewed}
                >
                  {label}
                </option>
              ))}
            </select>
            {!reviewed && (
              <span className="site-field-note">
                Review the current evidence before marking ready for handoff.
              </span>
            )}
          </label>
        </div>
      </section>
    </div>
  )
}
