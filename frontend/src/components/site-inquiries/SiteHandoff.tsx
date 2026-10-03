import { Button, StatusMessage } from '../ui'
import { handoffStageLabel, sitePacketSections } from '../../lib/sitePacket'
import type { SiteInquiry, SiteIntakePacket } from '../../types/siteIntake'

type Props = {
  inquiry: SiteInquiry
  packet: SiteIntakePacket
  busy: boolean
  error: string
  onClose: () => void
  onPrint: () => void
  onDownload: () => void
}

export default function SiteHandoff({
  inquiry,
  packet,
  busy,
  error,
  onClose,
  onPrint,
  onDownload,
}: Props) {
  const parcel = packet.report.parcel
  const reviewed = inquiry.reviewed_revision === packet.revision
  return (
    <div className="site-handoff-preview">
      <div className="site-toolbar site-screen-only">
        <Button onClick={onClose} disabled={busy}>
          Back to inquiry
        </Button>
        <Button tone="primary" onClick={onPrint} disabled={busy}>
          {busy ? 'Checking current evidence…' : 'Print / save PDF'}
        </Button>
        <Button onClick={onDownload} disabled={busy}>
          Download text
        </Button>
      </div>
      {error && (
        <div className="site-screen-only">
          <StatusMessage tone="error">{error}</StatusMessage>
        </div>
      )}
      <article className="site-handoff-document" aria-label="Research handoff preview">
        <header className="site-handoff-heading">
          <div className="page-eyebrow">CountyIQ · York County, Pennsylvania</div>
          <h1>{inquiry.label}</h1>
          <p className="site-handoff-subtitle">Site inquiry · Research handoff</p>
          <p>Prepared {new Date().toLocaleDateString('en-US', { dateStyle: 'long' })}</p>
        </header>
        <dl className="site-handoff-identity">
          <div>
            <dt>Property</dt>
            <dd>{parcel.propadr || 'Address not recorded'}</dd>
          </div>
          <div>
            <dt>Municipality</dt>
            <dd>{parcel.municipality || 'Unknown'}</dd>
          </div>
          <div>
            <dt>Parcel ID</dt>
            <dd>{inquiry.pidn}</dd>
          </div>
          <div>
            <dt>Recorded owner</dt>
            <dd>{parcel.owner_full || 'Unknown'}</dd>
          </div>
        </dl>
        <div className={`site-handoff-review ${reviewed ? 'site-handoff-reviewed' : ''}`}>
          <strong>
            {reviewed
              ? 'Current evidence reviewed by the user'
              : 'Research draft — evidence needs review'}
          </strong>
          <p>
            Workflow: {handoffStageLabel(inquiry, packet)}. Reviewer responses and proposed use are
            user input; they do not change the cited records.
          </p>
        </div>
        {sitePacketSections(inquiry, packet).map((section) => (
          <section key={section.title}>
            <h2>{section.title}</h2>
            {section.paragraphs.map((paragraph, index) => (
              <p key={index}>
                {/^https?:\/\//i.test(paragraph) ? (
                  <a href={paragraph} target="_blank" rel="noreferrer">
                    {paragraph}
                  </a>
                ) : (
                  paragraph
                )}
              </p>
            ))}
          </section>
        ))}
      </article>
    </div>
  )
}
