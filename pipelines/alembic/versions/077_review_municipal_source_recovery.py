"""Review York replacement identities, current archives, and browser transport.

The eight replacement bodies have new source keys. Previously misidentified
source policies and their retained evidence stay paused. Public record checks,
municipal identities, and transport evidence are recorded in the September 8
source audit; no private portals or denied delivery paths are enabled.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None

_REPLACEMENTS = [
    {
        "source_key": "penn_township_board_of_commissioners",
        "municipality_name": "PENN TWP",
        "body_name": "Penn Township Board of Commissioners",
        "listing_url": "https://penntwp.com/directory/committees/board-of-commissioners-meeting-minutes/",
        "proceeding_type": "board_of_commissioners",
        "sample_document": "https://penntwp.com/wp-content/uploads/2026/08/Board_of_Commissioners_Minutes_07_26.pdf",
        "robots_url": "https://penntwp.com/robots.txt",
    },
    {
        "source_key": "penn_township_planning_commission",
        "municipality_name": "PENN TWP",
        "body_name": "Penn Township Planning Commission",
        "listing_url": "https://penntwp.com/commissions/planning-commission/",
        "proceeding_type": "planning_commission",
        "sample_document": "https://penntwp.com/wp-content/uploads/2026/06/Planning-Minutes-05-2026.pdf",
        "robots_url": "https://penntwp.com/robots.txt",
    },
    {
        "source_key": "penn_township_zoning_hearing_board",
        "municipality_name": "PENN TWP",
        "body_name": "Penn Township Zoning Hearing Board",
        "listing_url": "https://penntwp.com/directory/boards/zoning-hearing-board/",
        "proceeding_type": "zoning_hearing",
        "sample_document": "https://penntwp.com/wp-content/uploads/2026/09/Penn-Township-0626.pdf",
        "robots_url": "https://penntwp.com/robots.txt",
    },
    {
        "source_key": "paradise_township_board_of_supervisors",
        "municipality_name": "PARADISE TWP",
        "body_name": "Paradise Township Board of Supervisors",
        "listing_url": "https://paradisetwpyorkco.com/board-of-supervisors-meeting-agendas-and-minutes/",
        "proceeding_type": "board_of_supervisors",
        "sample_document": "http://paradisetwpyorkco.com/wp-content/uploads/2026/08/MINUTES-07-13-26-TOWNSHIP-MEETING.pdf",
        "robots_url": "https://paradisetwpyorkco.com/robots.txt",
    },
    {
        "source_key": "paradise_township_planning_commission",
        "municipality_name": "PARADISE TWP",
        "body_name": "Paradise Township Planning Commission",
        "listing_url": "https://paradisetwpyorkco.com/planning-commission-meeting-agendas-and-minutes/",
        "proceeding_type": "planning_commission",
        "sample_document": "http://paradisetwpyorkco.com/wp-content/uploads/2026/07/20260518_PTPC_Meeting_Regular_Minutes.pdf",
        "robots_url": "https://paradisetwpyorkco.com/robots.txt",
    },
    {
        "source_key": "jackson_township_board_of_supervisors",
        "municipality_name": "JACKSON TWP",
        "body_name": "Jackson Township Board of Supervisors",
        "listing_url": "https://jacksontwpyork.org/township-calendar-meetings/township-meetings-minutes/board-of-supervisors-meetings-minutes",
        "proceeding_type": "board_of_supervisors",
        "sample_document": "https://jacksontwpyork.org/images/docs/10_07_25.pdf",
        "robots_url": "https://jacksontwpyork.org/robots.txt",
    },
    {
        "source_key": "windsor_township_board_of_supervisors",
        "municipality_name": "WINDSOR TWP",
        "body_name": "Windsor Township Board of Supervisors",
        "listing_url": "https://windsortwp.com/board-of-supervisors-meeting-minutes-agenda/",
        "proceeding_type": "board_of_supervisors",
        "sample_document": "https://windsortwp.com/wp-content/uploads/2026-07-20.pdf",
        "robots_url": "https://windsortwp.com/robots.txt",
    },
    {
        "source_key": "windsor_township_planning_commission",
        "municipality_name": "WINDSOR TWP",
        "body_name": "Windsor Township Planning Commission",
        "listing_url": "https://windsortwp.com/planning-commission-meeting-minutes-agenda/",
        "proceeding_type": "planning_commission",
        "sample_document": "https://windsortwp.com/wp-content/uploads/2026-05-21.pdf",
        "robots_url": "https://windsortwp.com/robots.txt",
    },
]

_LISTING_UPDATES = {
    "goldsboro_borough_council": "https://goldsboropa.com/council-minutes/",
    "hellam_twp_board_of_supervisors": "https://www.hellamtownship.gov/public-meetings-archive/",
    "hellam_twp_planning_commission": "https://www.hellamtownship.gov/public-meetings-archive/",
    "hellam_twp_zoning_hearing_board": "https://www.hellamtownship.gov/public-meetings-archive/",
    "delta_borough_council": "https://www.deltaborough.us/minutes-archive",
    "manchester_twp_board_of_supervisors": "https://www.mantwp.com/meeting-agenda-archive/",
    "dover_twp_planning_commission": "https://www.dovertownship.org/document-category/agendas-minutes/",
    "yorkana_borough_council": "https://yorkana-borough.com/meeting-minutes/",
}

_BROWSER_SOURCES = (
    "goldsboro_borough_council",
    "goldsboro_boro_planning_commission",
    "goldsboro_boro_zoning_hearing_board",
    "manheim_twp_board_of_supervisors",
    "north_york_borough_council",
    "peach_bottom_twp_board_of_supervisors",
    "springettsbury_twp_board_of_supervisors",
    "paradise_township_board_of_supervisors",
    "paradise_township_planning_commission",
)


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("""
            INSERT INTO meta.municipality_source_rights (
                source_key, county_key, municipality_name, body_name, listing_url,
                proceeding_type, rights_status, acquisition_allowed,
                raw_retention_allowed, derived_product_allowed,
                raw_export_allowed, allowed_methods,
                allowed_origins, terms_review_status, reviewed_on, review_due_on,
                evidence, notes
            )
            SELECT source_key, 'york', municipality_name, body_name, listing_url,
                proceeding_type, 'conditional', TRUE, TRUE, TRUE, FALSE,
                ARRAY['official_document_direct']::TEXT[],
                ARRAY[substring(listing_url from '^https://[^/]+')]::TEXT[],
                'not_found', DATE '2026-09-08', DATE '2026-12-08',
                jsonb_build_object(
                    'review', 'York jurisdiction verified; public meeting PDF retrieved and body checked',
                    'official_directory', 'https://www.ycpc.org/325/Municipal-Contacts',
                    'sample_document', sample_document,
                    'robots_url', robots_url,
                    'robots_review', 'public listing and document paths allowed',
                    'terms_review', 'no separate restrictive terms found on reviewed municipal navigation',
                    'identity_boundary', 'new source key; old wrong-county policies remain paused',
                    'evidence_report', 'docs/research/municipal-source-recovery-2026-09-08.md'
                ),
                'Reviewed official York municipal proceedings; public records only, finite requests, robots honored; no person-level display or raw export.'
            FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS reviewed(
                source_key TEXT, municipality_name TEXT, body_name TEXT,
                listing_url TEXT, proceeding_type TEXT, sample_document TEXT,
                robots_url TEXT
            )
        """),
        {"rows": json.dumps(_REPLACEMENTS)},
    )
    for source_key, listing_url in _LISTING_UPDATES.items():
        connection.execute(
            sa.text("""
                UPDATE meta.municipality_source_rights
                SET listing_url = :listing_url,
                    allowed_origins = ARRAY(
                        SELECT DISTINCT origin FROM unnest(
                            allowed_origins || ARRAY[substring(:listing_url from '^https://[^/]+')]
                        ) AS origin
                    ),
                    reviewed_on = DATE '2026-09-08', review_due_on = DATE '2026-12-08',
                    evidence = evidence || jsonb_build_object(
                        'listing_reviewed_on', '2026-09-08',
                        'listing_review', 'current official public archive; HTML minutes supported where published',
                        'evidence_report', 'docs/research/municipal-source-recovery-2026-09-08.md'
                    )
                WHERE source_key = :source_key AND county_key = 'york'
            """),
            {"source_key": source_key, "listing_url": listing_url},
        )
    connection.execute(
        sa.text("""
            UPDATE meta.municipality_source_rights
            SET evidence = evidence || jsonb_build_object(
                    'browser_transport_reviewed', TRUE,
                    'browser_transport_reviewed_on', '2026-09-08',
                    'browser_transport_basis',
                    'Public Chromium transport using its actual browser identity plus CountyIQ identification; robots checked in browser before listing; no credential or challenge bypass'
                ),
                reviewed_on = DATE '2026-09-08', review_due_on = DATE '2026-12-08'
            WHERE source_key = ANY(:source_keys) AND county_key = 'york'
        """),
        {"source_keys": list(_BROWSER_SOURCES)},
    )
    op.execute("""
        UPDATE meta.municipality_source_rights
        SET allowed_origins = array_append(allowed_origins, 'https://storage.googleapis.com'),
            evidence = evidence || jsonb_build_object(
                'document_origin_reviewed_on', '2026-09-08',
                'document_origin_basis', 'Official Hellam ProudCity meeting pages link public township PDFs in the proudcity/hellamtownshippa path; storage robots is absent (404)',
                'document_path_prefix', 'https://storage.googleapis.com/proudcity/hellamtownshippa/',
                'terms_review_url', 'https://cloud.google.com/terms/aup'
            )
        WHERE source_key IN ('hellam_twp_board_of_supervisors', 'hellam_twp_planning_commission', 'hellam_twp_zoning_hearing_board');
    """)


def downgrade() -> None:
    # Resuming old, misidentified sources is not a safe rollback. Preserve all
    # policy receipts and documents; a replacement forward review is required.
    raise RuntimeError(
        "Municipal source recovery requires a reviewed forward migration"
    )
