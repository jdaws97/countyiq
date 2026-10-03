import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom'

import Badge from '../components/Badge'
import EvidencePanel, { CitedText } from '../components/EvidencePanel'
import IntelligenceDecision from '../components/IntelligenceDecision'
import IntelligenceSavedWork from '../components/IntelligenceSavedWork'
import PageShell from '../components/PageShell'
import {
  Button,
  ButtonLink,
  EmptyState,
  Freshness,
  PageHeader,
  StatusMessage,
} from '../components/ui'
import { formatLabel, formatShortDate } from '../lib/format'
import { useFetchJson } from '../lib/useFetchJson'
import { useIntelligenceWorkspace } from '../lib/intelligenceWorkspace'
import {
  caseFit,
  matchingPossibilities,
  PROJECT_TYPES,
  READINESS,
  WORK_LABELS,
} from '../lib/intelligenceFlow'
import type {
  EmergingCase,
  EmergingCaseSummary,
  EmergingResponse,
  HypothesisFamily,
  IntelligenceProfile,
  IntelligenceWorkItem,
  OpportunityAudience,
  ProjectType,
  ActionReadiness,
} from '../types/emerging'

import './EmergingIntelligence.css'

const FAMILIES: HypothesisFamily[] = [
  'business_expansion',
  'land_assembly',
  'construction_timing',
  'infrastructure_unlock',
  'use_transition',
  'project_stall',
]

const WORK_STATUSES: IntelligenceWorkItem['status'][] = [
  'saved',
  'qualifying',
  'waiting',
  'acted',
  'rejected',
]

const SERVICES = [
  ['equipment_rental', 'Equipment rental'],
  ['sitework', 'Sitework'],
  ['construction', 'Construction'],
  ['engineering', 'Engineering'],
  ['surveying', 'Surveying'],
  ['electrical', 'Electrical'],
  ['mechanical', 'Mechanical'],
  ['specialty_installation', 'Specialty installation'],
  ['brokerage', 'Brokerage'],
] as const

const SERVICE_IDS: string[] = SERVICES.map(([value]) => value)

const PAGE_SIZE = 20

function resetPaging(params: URLSearchParams) {
  for (const key of ['cursor', 'back', 'offset']) {
    params.delete(key)
  }
}

export default function EmergingIntelligence() {
  const location = useLocation()
  const { caseKey } = useParams<{ caseKey: string }>()
  const opportunitiesMode = location.pathname === '/opportunities'
  if (caseKey) {
    return <IntelligenceDetail key={caseKey} caseKey={caseKey} />
  }

  return <IntelligenceList opportunitiesMode={opportunitiesMode} />
}

function IntelligenceList({ opportunitiesMode }: { opportunitiesMode: boolean }) {
  const location = useLocation()
  const { profile, work, setProfile, storageMessage } = useIntelligenceWorkspace()
  const [searchParams, setSearchParams] = useSearchParams()
  const canonicalReady = searchParams.has('filters')
  const [showProfile, setShowProfile] = useState(searchParams.has('edit_profile'))
  const query = searchParams.get('q') ?? ''
  const activeProfile = profileFromSearchParams(profile, searchParams)
  const view = location.pathname === '/my-work' ? 'work' : (searchParams.get('view') ?? 'for_you')
  useEffect(() => {
    if (searchParams.has('filters')) {
      return
    }
    const canonical = new URLSearchParams(searchParams)
    canonical.set('filters', 'custom')
    setRepeatedParams(canonical, 'family', activeProfile.families)
    setRepeatedParams(canonical, 'municipality', activeProfile.municipalities)
    setRepeatedParams(canonical, 'service', activeProfile.services)
    setRepeatedParams(canonical, 'project_type', activeProfile.project_types ?? [])
    setRepeatedParams(canonical, 'readiness', activeProfile.preferred_readiness ?? [])
    canonical.set('audience', activeProfile.audience)
    setSearchParams(canonical, { replace: true })
  }, [activeProfile, searchParams, setSearchParams])
  const params = new URLSearchParams(searchParams)
  const cursor = searchParams.get('cursor')
  const pagingState = location.state?.intelligencePaging
  const previousCursors: string[] =
    cursor &&
    pagingState?.cursor === cursor &&
    Array.isArray(pagingState.previousCursors) &&
    pagingState.previousCursors.every((value: unknown) => typeof value === 'string')
      ? pagingState.previousCursors
      : []
  params.delete('back')
  params.delete('offset')
  setRepeatedParams(params, 'family', activeProfile.families)
  setRepeatedParams(params, 'municipality', activeProfile.municipalities)
  setRepeatedParams(params, 'service', activeProfile.services)
  setRepeatedParams(params, 'project_type', activeProfile.project_types ?? [])
  setRepeatedParams(params, 'readiness', activeProfile.preferred_readiness ?? [])
  if (activeProfile.audience === 'all') {
    params.delete('audience')
  } else {
    params.set('audience', activeProfile.audience)
  }
  params.set('limit', String(PAGE_SIZE))
  if (opportunitiesMode) {
    params.set('opportunities_only', 'true')
  } else {
    params.delete('opportunities_only')
  }
  if (view === 'all' && !opportunitiesMode) {
    for (const key of [
      'audience',
      'family',
      'municipality',
      'service',
      'project_type',
      'readiness',
    ]) {
      params.delete(key)
    }
  } else {
    setRepeatedParams(
      params,
      'exclude_case_key',
      work.filter((item) => item.status === 'rejected').map((item) => item.case_key),
    )
  }
  const filterParams = new URLSearchParams(params)
  filterParams.delete('cursor')
  const filterKey = filterParams.toString()
  const previousFilters = useRef(filterKey)
  useEffect(() => {
    if (previousFilters.current !== filterKey && searchParams.has('cursor')) {
      const firstPage = new URLSearchParams(searchParams)
      resetPaging(firstPage)
      setSearchParams(firstPage, { replace: true })
    }
    previousFilters.current = filterKey
  }, [filterKey, searchParams, setSearchParams])
  const { data, loading, error, reload } = useFetchJson<EmergingResponse>(
    view === 'work' || !canonicalReady ? null : `/api/intelligence?${params}`,
  )

  const cases = data?.cases ?? []

  const updateFamilies = (value: HypothesisFamily) => {
    updateProfile({
      ...activeProfile,
      families: activeProfile.families.includes(value)
        ? activeProfile.families.filter((family) => family !== value)
        : [...activeProfile.families, value],
    })
  }

  const updateProfile = (nextProfile: IntelligenceProfile) => {
    setProfile(nextProfile)
    const nextParams = new URLSearchParams(searchParams)
    setRepeatedParams(nextParams, 'family', nextProfile.families)
    setRepeatedParams(nextParams, 'municipality', nextProfile.municipalities)
    setRepeatedParams(nextParams, 'service', nextProfile.services)
    setRepeatedParams(nextParams, 'project_type', nextProfile.project_types ?? [])
    setRepeatedParams(nextParams, 'readiness', nextProfile.preferred_readiness ?? [])
    if (nextProfile.audience === 'all') {
      nextParams.delete('audience')
    } else {
      nextParams.set('audience', nextProfile.audience)
    }
    resetPaging(nextParams)
    nextParams.set('view', 'for_you')
    setSearchParams(nextParams)
  }

  const updateQuery = (value: string) => {
    const nextParams = new URLSearchParams(searchParams)
    if (value.trim()) {
      nextParams.set('q', value)
    } else {
      nextParams.delete('q')
    }
    resetPaging(nextParams)
    setSearchParams(nextParams)
  }

  const movePage = (direction: 'next' | 'previous') => {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete('back')
    let nextHistory: string[]
    if (direction === 'next') {
      if (!data?.next_cursor) {
        return
      }
      nextHistory = [...previousCursors, cursor ?? '']
      nextParams.set('cursor', data.next_cursor)
    } else {
      const previous = previousCursors.at(-1)
      nextHistory = previousCursors.slice(0, -1)
      if (previous) {
        nextParams.set('cursor', previous)
      } else {
        nextParams.delete('cursor')
      }
    }
    setSearchParams(nextParams, {
      state: {
        intelligencePaging: {
          cursor: nextParams.get('cursor'),
          previousCursors: nextHistory,
        },
      },
    })
  }

  return (
    <PageShell maxWidth={1120} className="emerging-page">
      <PageHeader
        eyebrow={
          view === 'work'
            ? 'My workspace'
            : opportunitiesMode
              ? 'Opportunities'
              : 'Emerging intelligence'
        }
        title={
          view === 'work'
            ? 'Your cases, decisions and updates'
            : opportunitiesMode
              ? 'Commercial possibilities for your work'
              : 'Find the cases worth your attention'
        }
        description={
          view === 'work'
            ? 'Return to active investigations, review updated cases and keep your next steps together.'
            : opportunitiesMode
              ? 'Each case here has a specific commercial need, a reason to look now and an evidenced route to qualify it.'
              : 'Understand what may be changing, decide whether to pursue or follow it, and revisit your cases as the evidence develops.'
        }
        actions={
          <Button
            tone="quiet"
            onClick={() => setShowProfile((open) => !open)}
            aria-expanded={showProfile}
          >
            {showProfile ? 'Close work criteria' : 'My work criteria'}
          </Button>
        }
      />

      <nav className="intelligence-views" aria-label="Case views">
        {[
          ['/intelligence', 'for_you', 'For you'],
          ['/intelligence', 'all', 'All cases'],
          ['/opportunities', 'for_you', 'Opportunities'],
          ['/my-work', 'work', 'My work'],
        ].map(([path, nextView, label]) => {
          const next = new URLSearchParams(searchParams)
          next.set('view', nextView)
          resetPaging(next)
          const selected = opportunitiesMode
            ? path === '/opportunities'
            : path !== '/opportunities' && view === nextView
          return (
            <Link key={label} to={`${path}?${next}`} aria-current={selected ? 'page' : undefined}>
              {label}
            </Link>
          )
        })}
      </nav>
      {storageMessage && <p role="status">{storageMessage}</p>}
      {showProfile && (
        <section className="emerging-profile" aria-label="My work criteria">
          <label>
            My work
            <select
              value={activeProfile.audience}
              onChange={(event) =>
                updateProfile({
                  ...activeProfile,
                  audience: event.target.value as OpportunityAudience | 'all',
                  services: event.target.value === 'investor' ? [] : activeProfile.services,
                })
              }
            >
              <option value="all">Explore before choosing</option>
              <option value="investor">Investor / developer</option>
              <option value="service_business">Service business</option>
            </select>
          </label>
          <label>
            Municipalities, separated by commas
            <input
              key={searchParams.toString()}
              defaultValue={activeProfile.municipalities.join(', ')}
              onBlur={(event) =>
                updateProfile({
                  ...activeProfile,
                  municipalities: splitValues(event.target.value),
                })
              }
              placeholder="All municipalities"
            />
          </label>
          <fieldset
            disabled={activeProfile.audience === 'investor'}
            hidden={activeProfile.audience === 'investor'}
          >
            <legend>Services</legend>
            <div className="emerging-checkboxes">
              {SERVICES.map(([value, label]) => (
                <label key={value}>
                  <input
                    type="checkbox"
                    checked={activeProfile.services.includes(value)}
                    onChange={() =>
                      updateProfile({
                        ...activeProfile,
                        services: activeProfile.services.includes(value)
                          ? activeProfile.services.filter((service) => service !== value)
                          : [...activeProfile.services, value],
                      })
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>Changes I care about</legend>
            <div className="emerging-checkboxes">
              {FAMILIES.map((value) => (
                <label key={value}>
                  <input
                    type="checkbox"
                    checked={activeProfile.families.includes(value)}
                    onChange={() => updateFamilies(value)}
                  />
                  {formatLabel(value)}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>Project types</legend>
            <div className="emerging-checkboxes">
              {PROJECT_TYPES.map((type) => (
                <label key={type}>
                  <input
                    type="checkbox"
                    checked={activeProfile.project_types?.includes(type) ?? false}
                    onChange={() =>
                      updateProfile({
                        ...activeProfile,
                        project_types: toggleValue(activeProfile.project_types ?? [], type),
                      })
                    }
                  />
                  {formatLabel(type)}
                </label>
              ))}
            </div>
            <p className="emerging-scope">Unknown project types will not match a selected type.</p>
          </fieldset>
          <fieldset>
            <legend>When I want to get involved</legend>
            <div className="emerging-checkboxes">
              {READINESS.map(([stage, label]) => (
                <label key={stage}>
                  <input
                    type="checkbox"
                    checked={activeProfile.preferred_readiness?.includes(stage) ?? false}
                    onChange={() =>
                      updateProfile({
                        ...activeProfile,
                        preferred_readiness: toggleValue(
                          activeProfile.preferred_readiness ?? [],
                          stage,
                        ),
                      })
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
        </section>
      )}

      {view === 'work' ? (
        <IntelligenceSavedWork fullPage />
      ) : (
        <>
          {view !== 'all' && (
            <details className="intelligence-selection">
              <summary>How these cases are selected</summary>
              <p>
                Your saved criteria filter the shared pool of reviewed cases. Audience, service and
                timing must match the same commercial possibility; area, project type and topic
                further narrow the results. Dismissed cases are excluded.
              </p>
              <p>
                Cases are ordered by assessment date. Matching uses reviewed tags and does not learn
                from clicks or predict whether you will win work.{' '}
                {opportunitiesMode &&
                  'This view additionally requires a commercial need, timing reason and qualification route supported by evidence.'}
              </p>
              <p>
                <strong>Current criteria:</strong>{' '}
                {[
                  activeProfile.audience === 'all'
                    ? 'All business types'
                    : activeProfile.audience === 'investor'
                      ? 'Investor / developer'
                      : 'Service business',
                  ...activeProfile.services.map(
                    (value) => SERVICES.find(([id]) => id === value)?.[1] ?? formatLabel(value),
                  ),
                  ...activeProfile.municipalities,
                  ...(activeProfile.project_types ?? []).map(formatLabel),
                  ...activeProfile.families.map(formatLabel),
                  ...(activeProfile.preferred_readiness ?? []).map(
                    (value) => READINESS.find(([id]) => id === value)?.[1] ?? formatLabel(value),
                  ),
                ].join(' · ')}
              </p>
            </details>
          )}
          {view === 'all' && !opportunitiesMode && (
            <p className="emerging-scope">
              All reviewed cases, including those outside your criteria or previously dismissed.
            </p>
          )}
          {view !== 'all' && activeProfile.audience === 'all' && (
            <p className="intelligence-guidance">
              Choose your business, services and timing in{' '}
              <button onClick={() => setShowProfile(true)}>My work criteria</button> to focus this
              view.
            </p>
          )}
          <form className="emerging-search" onSubmit={(event) => event.preventDefault()}>
            <label>
              Search current intelligence
              <input value={query} onChange={(event) => updateQuery(event.target.value)} />
            </label>
          </form>

          {data?.coverage && <p className="emerging-scope">{data.coverage.note}</p>}
          {(loading || !canonicalReady) && (
            <StatusMessage>Loading current intelligence…</StatusMessage>
          )}
          {error && (
            <StatusMessage tone="error">
              Intelligence could not be loaded. <button onClick={reload}>Try again</button>
              {cursor && (
                <button
                  onClick={() => {
                    const firstPage = new URLSearchParams(searchParams)
                    resetPaging(firstPage)
                    setSearchParams(firstPage)
                  }}
                >
                  Return to the first page
                </button>
              )}
            </StatusMessage>
          )}
          {canonicalReady && !loading && !error && cases.length === 0 && (
            <EmptyState
              title={
                data?.has_more
                  ? 'No current cases in this page'
                  : opportunitiesMode
                    ? 'No qualified opportunities match your work yet'
                    : 'No current cases match your criteria'
              }
            >
              {data?.has_more
                ? 'These assessments need updated evidence. Continue to the next page to check more cases.'
                : opportunitiesMode
                  ? 'Early hypotheses and research questions remain in intelligence. Follow a relevant case while its commercial scope and timing become clearer.'
                  : 'Adjust your criteria or explore all reviewed cases. An empty result does not establish that no activity exists.'}
              <p>
                <Link to="/intelligence?view=all">Explore intelligence cases →</Link>
              </p>
            </EmptyState>
          )}
          <div className={opportunitiesMode ? 'opportunity-list' : 'emerging-list'}>
            {cases.map((item) => (
              <CaseCard
                key={item.case_key}
                item={item}
                profile={activeProfile}
                opportunitiesMode={opportunitiesMode}
              />
            ))}
          </div>
          {!loading && !error && data && (cursor || data.has_more) && (
            <nav className="emerging-pagination" aria-label="Intelligence pages">
              <Button tone="quiet" disabled={!cursor} onClick={() => movePage('previous')}>
                {cursor && previousCursors.length === 0 ? 'First page' : 'Previous'}
              </Button>
              <span>
                {cursor && previousCursors.length === 0
                  ? 'Current page'
                  : `Page ${previousCursors.length + 1}`}{' '}
                · {cases.length} current cases
              </span>
              <Button tone="quiet" disabled={!data.has_more} onClick={() => movePage('next')}>
                Next
              </Button>
            </nav>
          )}
        </>
      )}
    </PageShell>
  )
}

function CaseCard({
  item,
  profile,
  opportunitiesMode,
}: {
  item: EmergingCaseSummary
  profile: IntelligenceProfile
  opportunitiesMode: boolean
}) {
  const location = useLocation()
  const detailPath = `/intelligence/${encodeURIComponent(item.case_key)}${location.search}`

  return (
    <article className="emerging-case-card">
      <div className="emerging-card-topline">
        <span>{formatLabel(item.family)}</span>
        <span>{formatLabel(item.status)}</span>
      </div>
      <h2>
        <Link to={detailPath} state={location.state}>
          {item.title}
        </Link>
      </h2>
      <p className="emerging-hypothesis">{item.hypothesis}</p>
      <p className="emerging-fit">
        <strong>For your work:</strong> {caseFit(item, profile)}
      </p>
      {opportunitiesMode
        ? matchingPossibilities(item, profile, true).map((opportunity) => (
            <div key={opportunity.opportunity_key} className="emerging-commercial-summary">
              <strong>{opportunity.title}</strong>
              <p>{opportunity.rationale}</p>
              <p>
                <strong>Why now:</strong> {opportunity.commercial_basis?.timing}
              </p>
            </div>
          ))
        : item.supporting_facts[0] && (
            <p className="emerging-why">
              <strong>Evidence to review:</strong> {item.supporting_facts[0]}
            </p>
          )}
      <div className="emerging-card-meta">
        <Badge color="var(--accent-cyan)">{formatLabel(item.evidence_strength)} evidence</Badge>
        <span>Stage: {item.stage}</span>
        {item.municipalities.map((municipality) => (
          <span key={municipality}>{municipality}</span>
        ))}
      </div>
      <div className="emerging-card-footer">
        <Freshness value={item.as_of} label="Assessed" />
        <Link to={detailPath} state={location.state}>
          Open case and evidence →
        </Link>
      </div>
      <IntelligenceDecision item={item} />
    </article>
  )
}

function OpportunityCards({ item, profile }: { item: EmergingCase; profile: IntelligenceProfile }) {
  const location = useLocation()
  const detailPath = `/intelligence/${encodeURIComponent(item.case_key)}${location.search}`
  const opportunities = matchingPossibilities(item, profile, true)
  if (opportunities.length === 0) {
    return null
  }
  return opportunities.map((opportunity) => (
    <article className="opportunity-card" key={opportunity.opportunity_key}>
      <div className="emerging-card-topline">
        <span>{formatLabel(opportunity.audience)}</span>
        <span>{formatLabel(opportunity.readiness)}</span>
      </div>
      <h2>{opportunity.title}</h2>
      <p>
        <CitedText text={opportunity.rationale} evidence={item.citation_evidence} />
      </p>
      <p>
        <strong>Next action:</strong>{' '}
        <CitedText text={opportunity.next_action} evidence={item.citation_evidence} />
      </p>
      <p>
        <strong>Customer role:</strong>{' '}
        <CitedText text={opportunity.target_role} evidence={item.citation_evidence} />
      </p>
      {opportunity.commercial_basis && (
        <>
          <p>
            <strong>Commercial need:</strong>{' '}
            <CitedText text={opportunity.commercial_basis.need} evidence={item.citation_evidence} />
          </p>
          <p>
            <strong>Why now:</strong>{' '}
            <CitedText
              text={opportunity.commercial_basis.timing}
              evidence={item.citation_evidence}
            />
          </p>
          <p>
            <strong>Route to qualify:</strong>{' '}
            <CitedText
              text={opportunity.commercial_basis.qualification_route}
              evidence={item.citation_evidence}
            />
          </p>
        </>
      )}
      {opportunity.blockers.length > 0 && (
        <p>
          <strong>Blockers:</strong>{' '}
          {opportunity.blockers.map((blocker, index) => (
            <span key={blocker}>
              {index > 0 && '; '}
              <CitedText text={blocker} evidence={item.citation_evidence} />
            </span>
          ))}
        </p>
      )}
      {opportunity.disqualifiers.length > 0 && (
        <details>
          <summary>What would rule this out?</summary>
          <ul>
            {opportunity.disqualifiers.map((reason) => (
              <li key={reason}>
                <CitedText text={reason} evidence={item.citation_evidence} />
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="emerging-scope">
        Based on:{' '}
        <Link to={detailPath} state={location.state}>
          {item.title}
        </Link>
      </p>
    </article>
  ))
}

function IntelligenceDetail({ caseKey }: { caseKey: string }) {
  const location = useLocation()
  const { profile, work, saveCase, removeCase, storageMessage } = useIntelligenceWorkspace()
  const activeProfile = profileFromSearchParams(profile, new URLSearchParams(location.search))
  const [note, setNote] = useState('')
  const [noteDirty, setNoteDirty] = useState(false)
  const [status, setStatus] = useState<IntelligenceWorkItem['status']>('saved')
  const [statusDirty, setStatusDirty] = useState(false)
  const { data, loading, error, reload } = useFetchJson<EmergingCase>(
    `/api/intelligence/${encodeURIComponent(caseKey)}`,
  )
  const item = work.find((entry: IntelligenceWorkItem) => entry.case_key === caseKey)
  const selectedStatus = statusDirty ? status : (item?.status ?? status)
  const selectedNote = noteDirty ? note : (item?.note ?? note)

  if (loading) {
    return (
      <PageShell>
        <StatusMessage>Loading current hypothesis…</StatusMessage>
      </PageShell>
    )
  }
  if (error || !data) {
    return (
      <PageShell>
        <ButtonLink
          to={{ pathname: '/intelligence', search: location.search }}
          state={location.state}
          tone="quiet"
        >
          ← Back to emerging intelligence
        </ButtonLink>
        <EmptyState title="This hypothesis is unavailable">
          It may no longer be current in the supporting source scope. It has not been replaced with
          another case.
          <p>
            <Button onClick={reload}>Try again</Button>
          </p>
        </EmptyState>
      </PageShell>
    )
  }

  const revisionChanged = item && item.last_seen_revision !== data.revision
  return (
    <PageShell maxWidth={1040} className="emerging-page">
      <Link
        className="emerging-back"
        to={{ pathname: '/intelligence', search: location.search }}
        state={location.state}
      >
        ← Back to emerging intelligence
      </Link>
      {revisionChanged && (
        <StatusMessage>
          This case has been updated since your last review. Review the current account before
          deciding what to do next.
        </StatusMessage>
      )}
      <PageHeader
        eyebrow={formatLabel(data.family)}
        title={data.title}
        description={<CitedText text={data.hypothesis} evidence={data.citation_evidence} />}
        meta={
          <>
            <Badge color="var(--accent-cyan)">{formatLabel(data.evidence_strength)} evidence</Badge>{' '}
            <Badge color="var(--accent-gold)">{formatLabel(data.status)}</Badge>{' '}
            <Freshness value={data.as_of} label="Assessed" />
          </>
        }
      />
      <p className="emerging-scope">
        <CitedText text={data.scope_note} evidence={data.citation_evidence} />
      </p>
      <p>
        <strong>Current stage:</strong>{' '}
        <CitedText text={data.stage} evidence={data.citation_evidence} />
      </p>
      {data.change_summary && (
        <p className="emerging-change">
          <strong>Latest revision:</strong>{' '}
          <CitedText text={data.change_summary} evidence={data.citation_evidence} />
        </p>
      )}

      <section className="emerging-relevance" aria-label="Relevance to my work">
        <h2>For your work</h2>
        <p>
          {caseFit(data, activeProfile)}{' '}
          <Link to="/intelligence?edit_profile=1">Edit work criteria</Link>
        </p>
        <OpportunityCards item={data} profile={activeProfile} />
        {!matchingPossibilities(data, activeProfile, true).length && (
          <p>
            No qualified commercial action is established for your work. You can follow this case or
            pursue your own investigation.
          </p>
        )}
        {matchingPossibilities(data, activeProfile).filter(
          (possibility) => !data.opportunities.includes(possibility),
        ).length > 0 && (
          <details className="emerging-implications">
            <summary>Early implications and questions to resolve</summary>
            {matchingPossibilities(data, activeProfile)
              .filter((possibility) => !data.opportunities.includes(possibility))
              .map((possibility) => (
                <div key={possibility.opportunity_key}>
                  <p>
                    <CitedText text={possibility.rationale} evidence={data.citation_evidence} />
                  </p>
                  <p>
                    <strong>Still unresolved:</strong>{' '}
                    {possibility.blockers.map((blocker, index) => (
                      <span key={blocker}>
                        {index > 0 && '; '}
                        <CitedText text={blocker} evidence={data.citation_evidence} />
                      </span>
                    ))}
                  </p>
                </div>
              ))}
          </details>
        )}
        <IntelligenceDecision item={data} note={selectedNote} />
        <p className="emerging-scope">
          Pursue keeps this in your active work. Follow keeps it for later review. Dismiss removes
          it from For you and Opportunities. Updates appear in My work when you return; this does
          not send email alerts.
        </p>
        <Link to="/my-work">Open my work →</Link>
      </section>

      <section className="emerging-save" aria-label="Save this hypothesis to my work">
        <div>
          <strong>My decision and notes</strong>
          <span>Private to your workspace; it does not change the underlying hypothesis.</span>
        </div>
        <label>
          Status
          <select
            value={selectedStatus}
            onChange={(event) => {
              setStatus(event.target.value as IntelligenceWorkItem['status'])
              setStatusDirty(true)
            }}
          >
            {WORK_STATUSES.map((value) => (
              <option key={value} value={value}>
                {WORK_LABELS[value]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Note
          <textarea
            value={selectedNote}
            onChange={(event) => {
              setNote(event.target.value)
              setNoteDirty(true)
            }}
            placeholder="What should you check or decide next?"
          />
        </label>
        <div className="emerging-save-actions">
          <Button tone="primary" onClick={() => saveCase(data, selectedStatus, selectedNote)}>
            Save notes and decision
          </Button>
          {item && (
            <Button tone="quiet" onClick={() => removeCase(data.case_key)}>
              Remove
            </Button>
          )}
        </div>
        {revisionChanged && item && (
          <Button tone="quiet" onClick={() => saveCase(data, selectedStatus, selectedNote)}>
            Mark current case reviewed
          </Button>
        )}
        {storageMessage && <p role="status">{storageMessage}</p>}
      </section>

      <div className="emerging-detail-grid">
        <DetailList
          title="Supporting facts"
          values={data.supporting_facts}
          evidence={data.citation_evidence}
        />
        <DetailList
          title="Contrary evidence"
          values={data.contrary_evidence}
          evidence={data.citation_evidence}
          empty="No contrary evidence is currently recorded."
        />
        <section>
          <h2>Alternative explanations</h2>
          {data.alternatives.length ? (
            <div className="emerging-detail-list">
              {data.alternatives.map((alternative, index) => (
                <article key={index}>
                  <h3>
                    <CitedText text={alternative.explanation} evidence={data.citation_evidence} />
                  </h3>
                  <p>
                    <strong>Why plausible:</strong>{' '}
                    <CitedText text={alternative.why_plausible} evidence={data.citation_evidence} />
                  </p>
                  <p>
                    <strong>Check:</strong>{' '}
                    <CitedText
                      text={alternative.distinguishing_check}
                      evidence={data.citation_evidence}
                    />
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <p>No alternatives are currently recorded.</p>
          )}
        </section>
        <DetailList
          title="Unknowns"
          values={data.unknowns}
          empty="No unknowns are currently recorded."
        />
        <section>
          <h2>Next checks</h2>
          {data.next_checks.length ? (
            <div className="emerging-detail-list">
              {data.next_checks.map((check, index) => (
                <article key={index}>
                  <h3>
                    <CitedText text={check.question} evidence={data.citation_evidence} />
                  </h3>
                  <p>
                    <strong>Check:</strong>{' '}
                    <CitedText text={check.source_to_check} evidence={data.citation_evidence} />
                  </p>
                  <p>
                    <CitedText
                      text={check.why_it_changes_the_case}
                      evidence={data.citation_evidence}
                    />
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <p>No next checks are currently recorded.</p>
          )}
        </section>
        <section>
          <h2>Related places and activity</h2>
          <div className="emerging-links">
            {data.properties.map((property) => (
              <Link key={property.pidn} to={`/property/${encodeURIComponent(property.pidn)}`}>
                {property.address || property.pidn} <span>({property.relationship})</span>
              </Link>
            ))}
            {data.activity_links.map((link) => (
              <Link key={link.path} to={link.path}>
                {link.label}
              </Link>
            ))}
          </div>
        </section>
      </div>
      <EvidencePanel items={data.citation_evidence} title="View supporting sources" />
      <p className="emerging-scope">
        Latest record: {formatShortDate(data.latest_record_date) || 'Not available'} · Assessed{' '}
        {formatShortDate(data.assessed_at) || 'date unavailable'}
      </p>
    </PageShell>
  )
}

function DetailList({
  title,
  values,
  evidence,
  empty,
}: {
  title: string
  values: string[]
  evidence?: EmergingCase['citation_evidence']
  empty?: string
}) {
  return (
    <section>
      <h2>{title}</h2>
      {values.length ? (
        <ul className="emerging-detail-list">
          {values.map((value, index) => (
            <li key={index}>
              <CitedText text={value} evidence={evidence ?? []} />
            </li>
          ))}
        </ul>
      ) : (
        <p>{empty || `No ${title.toLowerCase()} are currently recorded.`}</p>
      )}
    </section>
  )
}

function splitValues(value: string) {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function toggleValue<T extends string>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((entry) => entry !== value) : [...values, value]
}

function setRepeatedParams(params: URLSearchParams, key: string, values: string[]) {
  params.delete(key)
  for (const value of values) {
    params.append(key, value)
  }
}

function profileFromSearchParams(
  profile: IntelligenceProfile,
  params: URLSearchParams,
): IntelligenceProfile {
  const families = params
    .getAll('family')
    .filter((value): value is HypothesisFamily => FAMILIES.includes(value as HypothesisFamily))
  const municipalities = params.getAll('municipality')
  const services = params.getAll('service').filter((value) => SERVICE_IDS.includes(value))
  const audience = params.get('audience') as OpportunityAudience | null
  const profileFamilies = profile.families.filter((value) => FAMILIES.includes(value))
  const profileServices = profile.services.filter((value) => SERVICE_IDS.includes(value))
  const projectTypes = params
    .getAll('project_type')
    .filter((value): value is ProjectType => PROJECT_TYPES.includes(value as ProjectType))
  const readiness = params
    .getAll('readiness')
    .filter((value): value is ActionReadiness => READINESS.some(([stage]) => stage === value))

  if (params.has('filters')) {
    return {
      audience: audience === 'investor' || audience === 'service_business' ? audience : 'all',
      families,
      municipalities,
      services,
      project_types: projectTypes,
      preferred_readiness: readiness,
    }
  }

  return {
    audience:
      audience === 'investor' || audience === 'service_business' ? audience : profile.audience,
    families: families.length > 0 ? families : profileFamilies,
    municipalities: municipalities.length > 0 ? municipalities : profile.municipalities,
    services: services.length > 0 ? services : profileServices,
    project_types: projectTypes.length ? projectTypes : (profile.project_types ?? []),
    preferred_readiness: readiness.length ? readiness : (profile.preferred_readiness ?? []),
  }
}
