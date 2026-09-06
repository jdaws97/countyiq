import { useState } from 'react'
import { siteUrls } from '../lib/siteUrls'

const VIEWS = ['Activity', 'Parcel map', 'Connections'] as const
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
  const [view, setView] = useState<PreviewView>('Activity')
  return (
    <div className="m-preview">
      <div className="m-preview-bar">
        <span className="m-preview-brand">
          CIQ <span>Your intelligence workspace</span>
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
        {view === 'Activity' && (
          <>
            <div className="m-preview-heading">
              <div>
                <span className="m-kicker">THE LOCAL PICTURE</span>
                <h3>Connect the dots.</h3>
              </div>
              <span className="m-small-tag">Source linked</span>
            </div>
            <div className="m-mini-map">
              <ParcelMap />
              <span className="m-map-label">A property. A plan. The bigger picture.</span>
            </div>
            <div className="m-event">
              <span className="m-event-icon" aria-hidden="true">
                ↗
              </span>
              <div>
                <span className="m-kicker">MUNICIPAL PROCEEDINGS</span>
                <h4>A subdivision is scheduled for review.</h4>
                <p>
                  Open the agenda, check the proposed site, and watch for the recorded decision.
                </p>
              </div>
            </div>
            <div className="m-evidence">
              <span>Meeting record</span>
              <i aria-hidden="true">→</i>
              <span>Linked parcel</span>
              <i aria-hidden="true">→</i>
              <span>Your watchlist</span>
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
        {view === 'Connections' && (
          <>
            <div className="m-preview-heading">
              <div>
                <span className="m-kicker">FOLLOW THE RELATIONSHIPS</span>
                <h3>Put ownership in context.</h3>
              </div>
            </div>
            <div className="m-connections">
              <div className="m-connection-source">
                Organization<span>A single place to investigate</span>
              </div>
              <div className="m-connection-line" />
              <div className="m-connection-children">
                <span>Property portfolio</span>
                <span>Linked projects</span>
                <span>Source records</span>
              </div>
            </div>
            <p className="m-preview-caption">
              Move from an organization to its properties and related activity, with evidence close
              at hand.
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
              <span /> PROPERTY INTELLIGENCE · YORK COUNTY, PA
            </div>
            <h1>
              Follow local development.
              <br />
              <em>See the evidence.</em>
            </h1>
            <p>
              For investors and developers working in York County. Review development proposals,
              investigate properties and recorded owners, and follow changes in the places you care
              about.
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
              Start with a property or municipality. Find the recorded activity, check the source,
              and decide what deserves a closer look.
            </p>
          </div>
          <div className="m-features">
            <article>
              <span className="m-feature-number">01</span>
              <div>
                <h3>Review local development activity.</h3>
                <p>
                  Bring municipal decisions, applications, and property activity into a single
                  intelligence feed. Open the original evidence when something catches your eye.
                </p>
                <span>Intelligence feed · Development radar</span>
              </div>
            </article>
            <article>
              <span className="m-feature-number">02</span>
              <div>
                <h3>Investigate a property and its owner.</h3>
                <p>
                  Move from a property to its recorded owner, other holdings, nearby parcels, and
                  source records. Check the evidence behind each connection.
                </p>
                <span>Property maps · Organization profiles · Case files</span>
              </div>
            </article>
            <article>
              <span className="m-feature-number">03</span>
              <div>
                <h3>Return to the changes you follow.</h3>
                <p>
                  Save properties, projects, and municipalities to your watches. Review new matching
                  activity in your workspace as source records are refreshed.
                </p>
                <span>Watchlists · Saved searches · Your workspace</span>
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
                <span>01 / DISCOVER</span>
                <h3>Find a signal.</h3>
                <p>
                  Start with recent activity, a development signal, or a property you already know.
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
                <span>03 / FOLLOW</span>
                <h3>Make it your focus.</h3>
                <p>Add it to your watches and pick up the investigation from your workspace.</p>
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
              We’re starting with York County, Pennsylvania, and refining CountyIQ with invited
              testers. Available records and coverage vary by source and municipality.
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
        <p>Property &amp; development intelligence.</p>
        <span>York County, Pennsylvania</span>
        <a href={app}>Sign in ↗</a>
      </footer>
    </div>
  )
}
