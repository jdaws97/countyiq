import { useState } from 'react'
import { siteUrls } from '../lib/siteUrls'

const VIEWS = ['Site inquiry', 'Parcel map', 'Research handoff'] as const
type PreviewView = (typeof VIEWS)[number]

function Brand() {
  return (
    <span className="m-brand">
      <svg viewBox="0 0 32 32" aria-hidden="true">
        <path d="m3 10 13-7 13 7-13 7Z" />
        <path d="m3 17 13 7 13-7M3 24l13 7 13-7" />
      </svg>
      County<span>IQ</span>
    </span>
  )
}

function ParcelMap() {
  return (
    <svg
      className="m-parcel-map"
      viewBox="0 0 600 370"
      role="img"
      aria-label="Illustrative parcel map with a highlighted site and nearby activity"
    >
      <defs>
        <pattern id="map-grid" width="24" height="24" patternUnits="userSpaceOnUse">
          <path d="M24 0H0V24" fill="none" stroke="#cbd5c9" strokeWidth=".5" />
        </pattern>
      </defs>
      <rect width="600" height="370" fill="#e6ebe0" />
      <rect width="600" height="370" fill="url(#map-grid)" />
      <path d="M470-30Q390 95 455 160T410 400" fill="none" stroke="#c1d9d5" strokeWidth="44" />
      <g fill="#d9e2cf" stroke="#aaba9f" strokeWidth="1.5">
        <path d="M-10 45 137 72 119 140-10 108Z" />
        <path d="m147 74 93 18-9 74-101-25Z" />
        <path d="m249 95 105 22-20 89-95-36Z" />
        <path d="m365 116 56 16 4 97-80-21Z" />
        <path d="m0 126 115 32-22 98-93-30Z" />
        <path d="m123 160 101 26-14 70-104 8Z" />
        <path d="m345 229 86 24-35 92-87-13Z" />
        <path d="m18 286 72-10-5 94H0Z" />
        <path d="m108 283 99-8 17 95H96Z" />
        <path d="m227 281 65 58-2 31h-52Z" />
        <path d="m493 27 107 23v87l-138-36Z" />
        <path d="m483 242 117 30v98H454Z" />
      </g>
      <path d="m244 189 90 33-30 100-83-64Z" fill="#cbd98d" stroke="#566e36" strokeWidth="2.5" />
      <path d="M-20 114 637 277M106-20 80 400" fill="none" stroke="#faf9f1" strokeWidth="13" />
      <path d="M-20 114 637 277M106-20 80 400" fill="none" stroke="#bfc4b8" strokeWidth="1" />
      <g fill="#607461" fontFamily="sans-serif" fontSize="10" letterSpacing="2">
        <text x="115" y="51">
          YORK COUNTY, PA
        </text>
        <text x="448" y="332">
          N
        </text>
      </g>
      <path d="m451 312 5 10h-10Z" fill="#607461" />
      <circle cx="284" cy="246" r="24" fill="#164b3b" opacity=".12" />
      <circle cx="284" cy="246" r="9" fill="#164b3b" stroke="#fff" strokeWidth="3" />
      <circle cx="176" cy="119" r="6" fill="#b48b42" stroke="#fff" strokeWidth="2" />
      <circle cx="372" cy="278" r="6" fill="#b48b42" stroke="#fff" strokeWidth="2" />
    </svg>
  )
}

function ProductPreview() {
  const [view, setView] = useState<PreviewView>('Site inquiry')
  return (
    <div className="m-preview">
      <div className="m-preview-bar">
        <span className="m-preview-brand">
          CIQ <span>Your site research workspace</span>
        </span>
        <span className="m-preview-dot" aria-hidden="true" />
      </div>
      <div className="m-preview-tabs" role="group" aria-label="Explore a product illustration">
        {VIEWS.map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={view === item}
            onClick={() => setView(item)}
          >
            {item}
          </button>
        ))}
      </div>
      <div className="m-preview-body" aria-live="polite">
        {view === 'Site inquiry' && (
          <>
            <div className="m-preview-heading">
              <div>
                <span className="m-kicker">START WITH THE CLIENT’S SITE</span>
                <h3>Prepare the first conversation.</h3>
              </div>
              <span className="m-small-tag">Source linked</span>
            </div>
            <div className="m-mini-map">
              <ParcelMap />
              <span className="m-map-label">Confirm the parcel and municipality.</span>
            </div>
            <div className="m-event">
              <span className="m-event-icon" aria-hidden="true">
                ↗
              </span>
              <div>
                <span className="m-kicker">MUNICIPAL PROCEEDINGS</span>
                <h4>What does the record establish?</h4>
                <p>
                  Check the original passage, its date and the stated action. Keep unanswered
                  questions visible.
                </p>
              </div>
            </div>
            <div className="m-evidence">
              <span>Meeting record</span>
              <i aria-hidden="true">→</i>
              <span>Linked parcel</span>
              <i aria-hidden="true">→</i>
              <span>Your site inquiry</span>
            </div>
          </>
        )}
        {view === 'Parcel map' && (
          <>
            <div className="m-preview-heading">
              <div>
                <span className="m-kicker">PLACE MATTERS</span>
                <h3>See beyond the boundary.</h3>
              </div>
            </div>
            <div className="m-full-map">
              <ParcelMap />
            </div>
            <p className="m-preview-caption">
              Bring parcels, zoning, infrastructure, and land-use context into the same view.
            </p>
          </>
        )}
        {view === 'Research handoff' && (
          <>
            <div className="m-preview-heading">
              <div>
                <span className="m-kicker">RESEARCH SOMEONE ELSE CAN CHECK</span>
                <h3>Carry the questions forward.</h3>
              </div>
            </div>
            <div className="m-connections">
              <div className="m-connection-source">
                Client inquiry<span>A candidate site and proposed use</span>
              </div>
              <div className="m-connection-line" />
              <div className="m-connection-children">
                <span>Cited findings</span>
                <span>Coverage gaps</span>
                <span>Open questions</span>
              </div>
            </div>
            <p className="m-preview-caption">
              Save private notes and export a research handoff with original links, source dates and
              unresolved questions.
            </p>
          </>
        )}
      </div>
      <div className="m-preview-footer">
        <span>Illustrative product view</span>
        <span>Built around the evidence ↗</span>
      </div>
    </div>
  )
}

export default function HomePage() {
  const { app } = siteUrls(window.location)
  return (
    <div className="marketing">
      <a className="m-skip" href="#main">
        Skip to content
      </a>
      <header className="m-nav m-wrap">
        <a href="/" aria-label="CountyIQ home">
          <Brand />
        </a>
        <nav aria-label="Main navigation">
          <a href="#platform">The platform</a>
          <a href="#workflow">How it works</a>
          <a href="#coverage">Coverage</a>
        </nav>
        <a className="m-nav-signin" href={app}>
          Sign in <span aria-hidden="true">↗</span>
        </a>
      </header>
      <main id="main">
        <section className="m-hero m-wrap">
          <div className="m-hero-copy">
            <div className="m-eyebrow">
              <span /> SITE INTAKE RESEARCH · YORK COUNTY, PA
            </div>
            <h1>
              A client brings a site.
              <br />
              <em>Know what to ask next.</em>
            </h1>
            <p>
              For civil engineering and land-planning teams in York County. Confirm the parcel,
              review mapped constraints and municipal records, and prepare a cited research handoff
              for the first municipal conversation.
            </p>
            <div className="m-actions">
              <a className="m-button" href="#workflow">
                See how it works <span aria-hidden="true">↓</span>
              </a>
              <a className="m-text-link" href={app}>
                Sign in to CountyIQ <span aria-hidden="true">↗</span>
              </a>
            </div>
            <div className="m-hero-note">
              <span className="m-location" aria-hidden="true">
                ◎
              </span>{' '}
              Starting in York County, Pennsylvania <span className="m-alpha">Private alpha</span>
            </div>
          </div>
          <div className="m-hero-visual">
            <div className="m-visual-caption">
              <span>01 / THE BIGGER PICTURE</span>
              <span>COUNTYIQ</span>
            </div>
            <ProductPreview />
            <div className="m-visual-footnote">
              Less searching across tabs. More understanding of the place.
            </div>
          </div>
        </section>
        <section className="m-source-strip" aria-label="Connected public records">
          <div className="m-wrap">
            <span>PUBLIC RECORDS, CONNECTED</span>
            <p>Municipal proceedings</p>
            <i aria-hidden="true">+</i>
            <p>Property records</p>
            <i aria-hidden="true">+</i>
            <p>Ownership relationships</p>
            <i aria-hidden="true">+</i>
            <p>Geographic context</p>
          </div>
        </section>
        <section id="platform" className="m-platform m-wrap">
          <div className="m-section-intro">
            <div className="m-eyebrow">THE ADVANTAGE IS CONTEXT</div>
            <h2>
              One address is only
              <br />
              <em>the beginning.</em>
            </h2>
            <p>
              Start with the client’s candidate property and intended use. Keep what the records
              establish separate from the questions that need a professional or municipal answer.
            </p>
          </div>
          <div className="m-features">
            <article>
              <span className="m-feature-number">01</span>
              <div>
                <h3>Confirm the site and its context.</h3>
                <p>
                  Identify the parcel and municipality. Review mapped zoning, flood coverage and
                  soils, with source freshness and missing coverage visible.
                </p>
                <span>Parcel identity · Mapped constraints · Source coverage</span>
              </div>
            </article>
            <article>
              <span className="m-feature-number">02</span>
              <div>
                <h3>Trace the municipal record.</h3>
                <p>
                  Read site-linked passages in their original documents. Distinguish proposed
                  business from recorded action, and see where collection or review is incomplete.
                </p>
                <span>Original passages · Meeting dates · Municipal context</span>
              </div>
            </article>
            <article>
              <span className="m-feature-number">03</span>
              <div>
                <h3>Hand off the research and questions.</h3>
                <p>
                  Save the proposed use, private notes and open questions. Export the research with
                  citations, and recheck the evidence when its revision changes.
                </p>
                <span>Private inquiries · Review state · Research export</span>
              </div>
            </article>
          </div>
        </section>
        <section id="workflow" className="m-workflow">
          <div className="m-wrap">
            <div className="m-workflow-top">
              <div>
                <div className="m-eyebrow">FROM RECORD TO UNDERSTANDING</div>
                <h2>
                  A clearer path to
                  <br />
                  your next question.
                </h2>
              </div>
              <p>
                Every investigation should lead back to something you can verify. CountyIQ keeps the
                source within reach and distinguishes interpretation from the record.
              </p>
            </div>
            <div className="m-steps">
              <article>
                <span>01 / IDENTIFY</span>
                <h3>Bring a candidate site.</h3>
                <p>
                  Find the client’s parcel and describe the intended use. Confirm the identity
                  before proceeding.
                </p>
              </article>
              <article>
                <span>02 / INVESTIGATE</span>
                <h3>Follow the evidence.</h3>
                <p>
                  Open the connected case file, compare the context, and read the original record.
                </p>
              </article>
              <article>
                <span>03 / HAND OFF</span>
                <h3>Keep the questions visible.</h3>
                <p>
                  Save your review and export the source trail, private notes and required
                  follow-up.
                </p>
              </article>
            </div>
          </div>
        </section>
        <section id="coverage" className="m-coverage m-wrap">
          <div className="m-coverage-mark" aria-hidden="true">
            PA<span>YORK COUNTY</span>
            <svg viewBox="0 0 200 110">
              <path d="M16 12 164 12 184 37 179 57 191 78 182 99H13V33l12-5Z" />
              <circle cx="143" cy="82" r="5" />
            </svg>
          </div>
          <div>
            <div className="m-eyebrow">LOCAL FIRST. BUILT TO GO DEEPER.</div>
            <h2>
              A county’s worth of context.
              <br />
              <em>One place to start.</em>
            </h2>
            <p>
              Private alpha for York County, Pennsylvania. Available records and coverage vary by
              source and municipality. The research supports proposal scoping; it does not determine
              permitted use, buildability, utility capacity or approval.
            </p>
            <a className="m-text-link" href={app}>
              Already invited? Open your workspace <span aria-hidden="true">↗</span>
            </a>
          </div>
        </section>
        <section className="m-closing m-wrap">
          <div>
            <div className="m-eyebrow">SEE THE PLACE. UNDERSTAND THE POSSIBILITIES.</div>
            <h2>
              Bring your next property
              <br />
              <em>question here.</em>
            </h2>
          </div>
          <div>
            <a className="m-button" href={app}>
              Sign in to CountyIQ <span aria-hidden="true">↗</span>
            </a>
            <p>Private alpha · Access for invited testers</p>
          </div>
        </section>
      </main>
      <footer className="m-footer m-wrap">
        <a href="/" aria-label="CountyIQ home">
          <Brand />
        </a>
        <p>Site research for the first municipal conversation.</p>
        <span>York County, Pennsylvania</span>
        <a href={app}>Sign in ↗</a>
      </footer>
    </div>
  )
}
