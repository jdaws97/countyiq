"""Enrichment: spatial-join radar overlay layers to parcels.

Emits parcel-linked signal evidence rows into public.development_signals.
Each signal type is a separate INSERT query. Full refresh each run.

RULES:
  - One row per (pidn, signal_key) — DISTINCT ON for all proximity/spatial joins
  - signal_weight is the deterministic ACTIVITY weight used by the momentum
    score. Opportunity uses the separately back-tested weights in
    development_momentum.py (see docs/research/radar-backtest-2026-09-02.md);
    no LLM output changes either score (score_version 7)
  - Recency matters: ownership_change and municipal_action decay by age so a
    sale last week and a sale eleven months ago are not the same signal
  - Proximity radii, price cutoffs, and neighbor thresholds live in
    county_config.py (signal_* fields) and are bound as query parameters
  - Exclude nominal transfers (price <= signal_nominal_sale_max)
  - Growth area: PGA/SGA only, low weight (tiebreaker, not differentiator)
  - Zoning mismatch: actual zoning (staging.zoning) vs future land use
  - Opportunity score should be anchored by direct parcel signals, not overlays
  - Flood zone: negative weight (discount, not exclude)
"""

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.intelligence_common import (
    RETRACT_STALE_EVIDENCE_QUERY,
    VOLATILE_EVIDENCE_KEYS,
)
from countyiq.lib.source_rights import authorize_source_uses, source_use_is_authorized
from countyiq.resources.database import DatabaseResource

# Word-bounded organisation markers. ``\m`` / ``\M`` are PostgreSQL word
# boundaries, so "PHILPOT" no longer matches "LP" and "ALPINE" no longer
# matches "INC".
BUSINESS_OWNER_REGEX = (
    r"\m(LLC|L\.L\.C|INC|CORP|CORPORATION|LP|L\.P|LLP|LTD|HOLDINGS|TRUST|"
    r"PARTNERS|PARTNERSHIP|ASSOCIATES|ENTERPRISES|PROPERTIES|GROUP|VENTURES|"
    r"CAPITAL|INVESTMENTS|DEVELOPMENT|REALTY|COMPANY|CO)\M"
)

_SIGNALS: list[tuple[str, str]] = [
    # A literal mention is useful investigation context, not an approval or a
    # calibrated opportunity score. Keep the source date/type and exact wording.
    (
        "municipal_record",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (reference.pidn)
            reference.pidn, 'municipal_record', 0,
            'public.current_municipal_evidence', source.event_key, NULL,
            jsonb_build_object(
                'event_key', source.event_key,
                'title', source.card->>'title',
                'meeting_date', source.meeting_date,
                'document_kind', source.payload->>'document_kind',
                'body_name', source.body_name,
                'source_url', source.document_url,
                'document_url', source.document_url,
                'passages', source.card->'passages',
                'matched_properties', source.matched_properties,
                'source_text_sha256', source.payload->>'source_text_sha256'
            )
        FROM public.current_municipal_evidence source
        CROSS JOIN LATERAL unnest(source.related_pidns) reference(pidn)
        WHERE source.meeting_date >= CURRENT_DATE - INTERVAL '24 months'
        ORDER BY reference.pidn, source.meeting_date DESC,
                 source.proceeding_id DESC, source.card_position
        """,
    ),
    # ── HIGH-VALUE DIRECT SIGNALS ──────────────────────────────────────
    # 1. active_subdivision — a believable plan point ON the parcel (inside the
    #    polygon or within 30 m of it), received in the last 3 years. This is
    #    the parcel's own activity; proximity-only matches go to
    #    nearby_subdivision so the label never claims a neighbour's plan.
    (
        "active_subdivision",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'active_subdivision', 0.30,
            'staging.planning_subdivisions', s.sequ_num,
            ST_Distance(p.geom::geography, s.geom::geography),
            jsonb_build_object(
                'plan_title', s.plan_title, 'date_rcvd', s.date_rcvd,
                'pt_subdiv', s.pt_subdiv, 'pt_land_dev', s.pt_land_dev,
                'total_acres', s.total_acres, 'prop_lots', s.prop_lots, 'prop_du', s.prop_du,
                'plan_location',
                    CASE
                        WHEN ST_Intersects(p.geom, s.geom) THEN 'point_on_parcel'
                        ELSE 'within_30m_of_parcel'
                    END,
                'months_since_received',
                    (EXTRACT(YEAR FROM AGE(NOW(), s.date_rcvd)) * 12
                     + EXTRACT(MONTH FROM AGE(NOW(), s.date_rcvd)))::int,
                'source_url', s.source_url
            )
        FROM staging.parcels p
        JOIN staging.planning_subdivisions s
            ON p.geom && ST_Expand(s.geom, %(subdivision_on_parcel_deg)s)
           AND ST_DWithin(p.geom::geography, s.geom::geography, %(subdivision_on_parcel_m)s)
        WHERE p.valid_to IS NULL AND s.valid_to IS NULL
          AND p.geom IS NOT NULL
          AND s.date_rcvd >= NOW() - INTERVAL '3 years'
          -- Believability filter (see the hybrid-LLM decision in docs/decisions.md):
          -- plans with prop_du=0 AND pt_land_dev=NO were 20,773 of the raw
          -- signals and 0%% were ever confirmed — the LLM downgraded every
          -- one with identical reasoning. Filter at the source instead of
          -- paying Pass 2 to rediscover it per parcel.
          AND (COALESCE(s.prop_du, 0) > 0
               OR UPPER(COALESCE(s.pt_land_dev, 'NO')) = 'YES')
        ORDER BY p.pidn, ST_Distance(p.geom::geography, s.geom::geography), s.date_rcvd DESC
        """,
    ),
    # 1b. nearby_subdivision — closest believable plan beyond the on-parcel
    #     band but within the corridor radius. Neighbourhood activity is a
    #     real predictor (see the back-test) but it is not this parcel's plan.
    (
        "nearby_subdivision",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'nearby_subdivision', 0.08,
            'staging.planning_subdivisions', s.sequ_num,
            ST_Distance(p.geom::geography, s.geom::geography),
            jsonb_build_object(
                'plan_title', s.plan_title, 'date_rcvd', s.date_rcvd,
                'pt_subdiv', s.pt_subdiv, 'pt_land_dev', s.pt_land_dev,
                'total_acres', s.total_acres, 'prop_lots', s.prop_lots, 'prop_du', s.prop_du,
                'plan_location', 'nearby',
                'distance_m', ROUND(ST_Distance(p.geom::geography, s.geom::geography)::numeric),
                'source_url', s.source_url
            )
        FROM staging.parcels p
        JOIN staging.planning_subdivisions s
            ON p.geom && ST_Expand(s.geom, %(subdivision_radius_deg)s)
           AND ST_DWithin(p.geom::geography, s.geom::geography, %(subdivision_radius_m)s)
        WHERE p.valid_to IS NULL AND s.valid_to IS NULL
          AND p.geom IS NOT NULL
          AND s.date_rcvd >= NOW() - INTERVAL '3 years'
          AND (COALESCE(s.prop_du, 0) > 0
               OR UPPER(COALESCE(s.pt_land_dev, 'NO')) = 'YES')
          AND NOT EXISTS (
              SELECT 1 FROM public.development_signals x
              WHERE x.pidn = p.pidn AND x.signal_key = 'active_subdivision'
          )
        ORDER BY p.pidn, ST_Distance(p.geom::geography, s.geom::geography), s.date_rcvd DESC
        """,
    ),
    # 2. economic_development_park — official open-data park designation
    (
        "economic_development_park",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT
            p.pidn,
            'economic_development_park',
            CASE WHEN BOOL_OR(ep.park_type = 'industrial') THEN 0.18 ELSE 0.15 END,
            'staging.economic_development_parks',
            STRING_AGG(DISTINCT ep.park_type || ':' || ep.source_objectid, ','),
            NULL,
            jsonb_build_object(
                'park_types', jsonb_agg(DISTINCT ep.park_type),
                'park_names', jsonb_agg(DISTINCT ep.name) FILTER (WHERE ep.name IS NOT NULL),
                'source_records', jsonb_agg(DISTINCT jsonb_build_object(
                    'park_type', ep.park_type,
                    'objectid', ep.source_objectid,
                    'source_url', ep.source_url
                )),
                'source_url', MIN(ep.source_url)
            )
        FROM staging.parcels p
        JOIN staging.economic_development_parks ep
            ON ep.pidn = p.pidn AND ep.valid_to IS NULL
        WHERE p.valid_to IS NULL
        GROUP BY p.pidn
        """,
    ),
    # 2b. municipal_action — the parcel is the subject of a rezoning, variance,
    #     special exception, conditional use, or land-development matter in
    #     Pass 0 municipal proceedings within the last 24 months. Linking is
    #     deterministic (normalized alphanumeric PIDN or the normalized street
    #     address, see migration 053); the
    #     weight follows the procedural state and decays with age.
    (
        "municipal_action",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (m.pidn)
            m.pidn,
            'municipal_action',
            ROUND((
                CASE
                    WHEN m.decision = 'approved' THEN 0.20
                    WHEN m.decision = 'denied' THEN 0.04
                    ELSE 0.14
                END
                * CASE
                    WHEN m.months_since <= 6 THEN 1.0
                    WHEN m.months_since <= 12 THEN 0.8
                    ELSE 0.6
                END
            )::numeric, 4),
            'staging.proceeding_extractions',
            m.extraction_id::text,
            NULL,
            jsonb_build_object(
                'extraction_type', m.extraction_type,
                'decision', m.decision,
                'meeting_date', m.meeting_date,
                'months_since_meeting', m.months_since,
                'body_name', m.body_name,
                'project_name', m.project_name,
                'proposed_zoning', m.proposed_zoning,
                'event_tags', m.event_tags,
                'match_method', m.match_method,
                'source_url', COALESCE(m.document_url, m.source_url)
            )
        FROM (
            SELECT
                p.pidn,
                pe.id AS extraction_id,
                pe.extraction_type,
                LOWER(pe.decision) AS decision,
                pe.project_name,
                pe.proposed_zoning,
                pe.event_tags,
                pp.body_name,
                pp.meeting_date,
                pp.document_url,
                pp.source_url,
                (EXTRACT(YEAR FROM AGE(NOW(), pp.meeting_date)) * 12
                 + EXTRACT(MONTH FROM AGE(NOW(), pp.meeting_date)))::int AS months_since,
                CASE
                    WHEN matched.match_method = 'pidn'
                        THEN 'pidn'
                    ELSE 'normalized_address'
                END AS match_method
            FROM staging.proceeding_extractions pe
            JOIN staging.public_proceedings pp
              ON pp.id = pe.proceeding_id AND pp.valid_to IS NULL
            CROSS JOIN LATERAL public.proceeding_parcel_matches(
                COALESCE(pe.extraction_details->'parcel_references', jsonb_build_array(pe.parcel_reference)),
                pp.body_name) matched
            JOIN staging.parcels p
              ON p.valid_to IS NULL AND p.pidn = matched.pidn
            WHERE LEFT(pe.extraction_type, 1) <> '_'
              AND pe.extraction_details->>'discovery_eligible' IS DISTINCT FROM 'false'
              AND pp.meeting_date IS NOT NULL
              AND pp.meeting_date >= NOW() - INTERVAL '24 months'
        ) m
        ORDER BY m.pidn, m.meeting_date DESC, m.extraction_id DESC
        """,
    ),
    # ── MEDIUM-VALUE CONTEXT SIGNALS ───────────────────────────────────
    # 3. zoning_mismatch — actual zoning vs future land use
    (
        "zoning_mismatch",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'zoning_mismatch', 0.10,
            'staging.future_landuse', f.globalid, NULL,
            jsonb_build_object(
                'current_ztype', z.ztype, 'current_zname', z.zname,
                'current_zoning_id', z.zrecid,
                'current_zoning_adopted', z.adpt_date,
                'current_zoning_source_url', z.source_url,
                'future_lu', f.future_lu, 'general_lu', f.general_lu,
                'future_land_use_adopted', f.adopt_date,
                'basis', 'parcel_center',
                'source_url', f.source_url
            )
        FROM staging.parcels p
        CROSS JOIN LATERAL public.parcel_center_zoning(p.geom) z
        CROSS JOIN LATERAL (
            SELECT f.* FROM staging.future_landuse f
            WHERE f.valid_to IS NULL AND ST_Intersects(ST_Centroid(p.geom), f.geom)
            ORDER BY f.adopt_date DESC NULLS LAST, f.globalid
            LIMIT 1
        ) f
        WHERE p.valid_to IS NULL
          AND f.future_lu IS NOT NULL AND f.future_lu != 'NO FUTURE LANDUSE'
          -- Some source category codes contradict both district labels. Do
          -- not infer a divergence from that code; the report still shows the
          -- original zoning record. This is a label screen, not an ordinance.
          AND CASE z.ztype
              WHEN 'R' THEN CONCAT_WS(' ', z.zname, z.gen_zname) ~* 'residen'
              WHEN 'C' THEN CONCAT_WS(' ', z.zname, z.gen_zname) ~* 'commer|business|office|shopping|retail|employment'
              WHEN 'A' THEN CONCAT_WS(' ', z.zname, z.gen_zname) ~* 'agri|farm'
              WHEN 'I' THEN CONCAT_WS(' ', z.zname, z.gen_zname) ~* 'industr|manufactur'
              WHEN 'M' THEN CONCAT_WS(' ', z.zname, z.gen_zname) ~* 'mixed'
              ELSE FALSE
          END
          AND (
              (z.ztype = 'R' AND f.general_lu NOT ILIKE '%%resident%%')
              OR (z.ztype = 'C' AND f.general_lu NOT ILIKE '%%commer%%')
              OR (z.ztype = 'A' AND f.general_lu NOT ILIKE '%%agri%%')
              OR (z.ztype = 'I' AND f.general_lu NOT ILIKE '%%industr%%')
              OR (z.ztype = 'M' AND f.general_lu NOT ILIKE '%%mixed use%%')
          )
          -- Exclude false mismatches where zoning name matches future use
          AND LOWER(REPLACE(z.zname, ' ', '')) != LOWER(REPLACE(f.future_lu, ' ', ''))
          AND f.future_lu NOT ILIKE '%%' || z.zname || '%%'
          AND z.zname NOT ILIKE '%%' || f.future_lu || '%%'
        -- Selection happens before the mismatch filter, as in property reports.
        -- M is mixed use in the county layer, not manufacturing. Preserve its
        -- original future-use spelling in evidence, including "Commerical".
        ORDER BY p.pidn, f.adopt_date DESC NULLS LAST, f.globalid
        """,
    ),
    # 4. ownership_change — real market sale in the last 12 months. The weight
    #    decays with age (a sale last quarter is a stronger signal than one
    #    eleven months ago). Buyer-type detection uses word boundaries so
    #    surnames containing "LP" or "INC" are not labelled investor buyers.
    (
        "ownership_change",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT
            x.pidn, 'ownership_change',
            CASE
                WHEN x.months_since_sale <= 3 THEN 0.10
                WHEN x.months_since_sale <= 6 THEN 0.08
                ELSE 0.06
            END,
            'staging.parcels', x.pidn, NULL,
            jsonb_build_object(
                'saledt', x.saledt, 'price', x.price, 'prev_owner', x.prev_owner,
                'months_since_sale', x.months_since_sale,
                'price_to_assessed_pct',
                    CASE WHEN COALESCE(x.aprtotal::numeric, 0) > 0
                         THEN ROUND(100 * x.price::numeric / x.aprtotal::numeric)
                         ELSE NULL END,
                'buyer_name_looks_organizational', x.buyer_is_business,
                'source_url', x.source_url
            )
        FROM (
            SELECT
                p.pidn, p.saledt, p.price, p.prev_owner, p.aprtotal, p.source_url,
                (EXTRACT(YEAR FROM AGE(NOW(), to_date(p.saledt, 'DD-MON-YYYY'))) * 12
                 + EXTRACT(MONTH FROM AGE(NOW(), to_date(p.saledt, 'DD-MON-YYYY'))))::int
                    AS months_since_sale,
                COALESCE(p.owner_full, '') ~* %(business_owner_regex)s AS buyer_is_business
            FROM staging.parcels p
            WHERE p.valid_to IS NULL
              -- Format guard: a single malformed county date must not abort the
              -- whole rebuild (all inserts share one transaction).
              AND p.saledt ~* '^\\d{1,2}-[a-z]{3}-\\d{4}$'
              AND to_date(p.saledt, 'DD-MON-YYYY') >= NOW() - INTERVAL '12 months'
              AND to_date(p.saledt, 'DD-MON-YYYY') <= NOW()
              AND COALESCE(p.price::numeric, 0) > %(nominal_sale_max)s
        ) x
        """,
    ),
    # 5. vacancy — no structures + not high-value residential + no recent high-dollar sale
    (
        "vacancy",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT p.pidn, 'vacancy', 0.12,
            'staging.structures', p.pidn, NULL,
            jsonb_build_object(
                'structure_count', 0,
                'class', p.class,
                'aprtotal', p.aprtotal,
                'price', p.price,
                'screen_basis', 'no_intersecting_county_building_footprint_and_low_value_filters',
                'source_url', p.source_url
            )
        FROM staging.parcels p
        WHERE p.valid_to IS NULL
          AND p.geom IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM staging.structures s
              WHERE s.valid_to IS NULL
                AND s.geom IS NOT NULL
                AND ST_Intersects(s.geom, p.geom)
          )
          AND (p.class NOT IN ('R') OR p.aprtotal IS NULL OR p.aprtotal::numeric < %(vacancy_apr_max)s)
          AND (p.price IS NULL OR p.price::numeric < %(vacancy_price_max)s)
        """,
    ),
    # 6. tax_distress — active tax delinquency (redevelopment signal)
    (
        "tax_distress",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT
            agg.pidn, 'tax_distress', 0.10,
            'staging.tax_claims', agg.pidn, NULL,
            jsonb_build_object(
                'total_owed', agg.total_owed,
                'years_delinquent', agg.years_delinquent,
                'oldest_year', agg.oldest_year,
                'source_url', agg.source_url
            )
        FROM (
            SELECT tc.pidn,
                   SUM(tc.total) AS total_owed,
                   COUNT(DISTINCT tc.tax_year) AS years_delinquent,
                   MIN(tc.tax_year) AS oldest_year,
                   MAX(tc.source_url) AS source_url
            FROM staging.tax_claims tc
            JOIN staging.parcels p ON p.pidn = tc.pidn AND p.valid_to IS NULL
            WHERE tc.valid_to IS NULL
            GROUP BY tc.pidn
            HAVING SUM(tc.total) > 0
        ) agg
        """,
    ),
    # 7. assemblage — touches many differently owned parcels. Ownership is
    #    compared on the resolved owner identity (public.owner_source_links,
    #    which merges spelling, punctuation, and suffix variants and Pass 1
    #    merges) with the raw recorded name as the fallback, so "SMITH JOHN"
    #    and "SMITH JOHN A" are one owner, not two.
    (
        "assemblage",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        WITH resolved AS (
            -- One resolved owner per current parcel. The parcel self-join
            -- below stays on staging.parcels so its geometry index is used; a
            -- materialized CTE over all parcels would lose that index.
            SELECT DISTINCT ON (source_id) source_id AS pidn, owner_id
            FROM public.owner_source_links
            WHERE source_type = 'parcel'
            ORDER BY source_id, owner_id
        ),
        neighbors AS (
            SELECT
                p.pidn,
                p.source_url,
                CASE
                    WHEN po.owner_id IS NOT NULL THEN 'owner:' || po.owner_id::text
                    WHEN NULLIF(TRIM(p.owner_full), '') IS NOT NULL
                        THEN 'raw:' || UPPER(TRIM(p.owner_full))
                END AS owner_key,
                n.pidn AS neighbor_pidn,
                CASE
                    WHEN nb.owner_id IS NOT NULL THEN 'owner:' || nb.owner_id::text
                    WHEN NULLIF(TRIM(n.owner_full), '') IS NOT NULL
                        THEN 'raw:' || UPPER(TRIM(n.owner_full))
                END AS neighbor_owner_key
            FROM staging.parcels p
            JOIN staging.parcels n
                ON n.valid_to IS NULL
               AND n.geom IS NOT NULL
               AND p.pidn <> n.pidn
               -- ST_Intersects, not ST_Touches: county parcel polygons often
               -- overlap slightly, which makes interiors intersect and silently
               -- fails the strict touch test.
               AND p.geom && n.geom
               AND ST_Intersects(p.geom, n.geom)
            LEFT JOIN resolved po ON po.pidn = p.pidn
            LEFT JOIN resolved nb ON nb.pidn = n.pidn
            WHERE p.valid_to IS NULL
              AND p.geom IS NOT NULL
        )
        SELECT
            pidn,
            'assemblage',
            CASE
                WHEN COUNT(DISTINCT neighbor_owner_key) FILTER (
                    WHERE neighbor_owner_key IS DISTINCT FROM owner_key
                ) >= %(assemblage_strong_neighbors)s THEN 0.10
                ELSE 0.06
            END,
            'staging.parcels',
            pidn,
            NULL,
            jsonb_build_object(
                'different_owner_neighbors',
                COUNT(DISTINCT neighbor_owner_key) FILTER (
                    WHERE neighbor_owner_key IS DISTINCT FROM owner_key
                ),
                'neighbor_parcels',
                COUNT(DISTINCT neighbor_pidn) FILTER (
                    WHERE neighbor_owner_key IS DISTINCT FROM owner_key
                ),
                'match_basis', 'resolved_owner_identity',
                'source_url', MIN(source_url)
            )
        FROM neighbors
        GROUP BY pidn, owner_key
        HAVING COUNT(DISTINCT neighbor_owner_key) FILTER (
            WHERE neighbor_owner_key IS DISTINCT FROM owner_key
        ) >= %(assemblage_min_neighbors)s
        """,
    ),
    # 7b. entity_assemblage — one owner holds two or more contiguous parcels
    #     and acquired at least one of them in the last 24 months. This is the
    #     developer-intent pattern (an entity accumulating a site); the older
    #     `assemblage` signal only measures how fragmented the neighbourhood
    #     is. Every parcel in the accumulating cluster receives the signal.
    (
        "entity_assemblage",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        WITH resolved AS (
            SELECT DISTINCT ON (source_id) source_id AS pidn, owner_id
            FROM public.owner_source_links
            WHERE source_type = 'parcel'
            ORDER BY source_id, owner_id
        ),
        owner_keys AS (
            -- Resolved owner identity (name variants and Pass 1 merges folded
            -- into one key), raw recorded name as the fallback.
            SELECT
                p.pidn,
                p.geom,
                p.source_url,
                p.saledt,
                p.price,
                CASE
                    WHEN r.owner_id IS NOT NULL THEN 'owner:' || r.owner_id::text
                    WHEN NULLIF(TRIM(p.owner_full), '') IS NOT NULL
                        THEN 'raw:' || UPPER(TRIM(p.owner_full))
                END AS owner_key
            FROM staging.parcels p
            LEFT JOIN resolved r ON r.pidn = p.pidn
            WHERE p.valid_to IS NULL AND p.geom IS NOT NULL
        ),
        recent AS (
            SELECT
                p.pidn,
                p.owner_key,
                p.geom,
                p.source_url,
                to_date(p.saledt, 'DD-MON-YYYY') AS sale_date
            FROM owner_keys p
            WHERE p.owner_key IS NOT NULL
              AND p.saledt ~* '^\\d{1,2}-[a-z]{3}-\\d{4}$'
              AND to_date(p.saledt, 'DD-MON-YYYY') >= NOW() - INTERVAL '24 months'
              AND to_date(p.saledt, 'DD-MON-YYYY') <= NOW()
              AND COALESCE(p.price::numeric, 0) > %(nominal_sale_max)s
        ),
        pairs AS (
            SELECT r.pidn AS seed_pidn, r.owner_key, r.sale_date,
                   r.source_url, n.pidn AS neighbor_pidn
            FROM recent r
            JOIN owner_keys n
              ON n.pidn <> r.pidn
             AND n.owner_key = r.owner_key
             AND r.geom && n.geom
             AND ST_Intersects(r.geom, n.geom)
        ),
        members AS (
            SELECT seed_pidn AS pidn, owner_key, sale_date, source_url,
                   neighbor_pidn AS other_pidn FROM pairs
            UNION ALL
            SELECT neighbor_pidn, owner_key, sale_date, source_url,
                   seed_pidn FROM pairs
        ),
        agg AS (
            SELECT
                pidn,
                owner_key,
                COUNT(DISTINCT other_pidn) AS contiguous_same_owner,
                MAX(sale_date) AS latest_acquisition,
                MIN(source_url) AS source_url
            FROM members
            GROUP BY pidn, owner_key
        )
        SELECT
            a.pidn,
            'entity_assemblage',
            CASE WHEN a.contiguous_same_owner >= 2 THEN 0.15 ELSE 0.10 END,
            'staging.parcels',
            a.pidn,
            NULL,
            jsonb_build_object(
                'contiguous_same_owner_parcels', a.contiguous_same_owner + 1,
                'latest_acquisition', a.latest_acquisition,
                'months_since_latest_acquisition',
                    (EXTRACT(YEAR FROM AGE(NOW(), a.latest_acquisition)) * 12
                     + EXTRACT(MONTH FROM AGE(NOW(), a.latest_acquisition)))::int,
                'match_basis', 'resolved_owner_identity_and_intersecting_parcels',
                'source_url', a.source_url
            )
        FROM agg a
        """,
    ),
    # ── LOW-VALUE PROXIMITY / CONTEXT SIGNALS ──────────────────────────
    # 8. penndot_project — closest within 800m
    #    Evidence includes full project metadata so Pass 2 LLM can assess
    #    currency (active vs completed), scale (cost), and impact window.
    (
        "penndot_project",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'penndot_project', 0.03,
            'staging.penndot_projects', pp.project_id,
            ST_Distance(ST_Centroid(p.geom)::geography, pp.geom::geography),
            jsonb_build_object(
                'project_name', pp.project_name,
                'project_id', pp.project_id,
                'description', LEFT(COALESCE(pp.description, ''), 300),
                'status', pp.status,
                'project_type', pp.project_type,
                'start_date', pp.start_date,
                'end_date', pp.end_date,
                'cost', pp.cost,
                'municipality', pp.municipality,
                'source_url', pp.source_url
            )
        FROM staging.parcels p
        JOIN staging.penndot_projects pp
            ON p.geom && ST_Expand(pp.geom, %(infrastructure_radius_deg)s)
           AND ST_DWithin(ST_Centroid(p.geom)::geography, pp.geom::geography, %(infrastructure_radius_m)s)
        WHERE p.valid_to IS NULL AND pp.valid_to IS NULL
          AND COALESCE(pp.status, '') NOT ILIKE '%%complete%%'
        ORDER BY p.pidn, ST_Distance(ST_Centroid(p.geom)::geography, pp.geom::geography)
        """,
    ),
    # 9. development_overlay — parcel is inside an expressly development-focused overlay
    (
        "development_overlay",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'development_overlay', 0.04,
            'staging.zoning_overlays', zo.globalid, NULL,
            jsonb_build_object(
                'overlay_type', zo.overlay_type,
                'overlay_name', zo.overlay_name,
                'description', zo.description,
                'municipality', zo.municipality,
                'basis', 'parcel_center',
                'source_url', zo.source_url
            )
        FROM staging.parcels p
        JOIN staging.zoning_overlays zo
            ON ST_Intersects(ST_Centroid(p.geom), zo.geom)
        WHERE p.valid_to IS NULL
          AND zo.valid_to IS NULL
          AND zo.overlay_type = 'DEVELOPMENT'
        ORDER BY p.pidn, zo.overlay_name
        """,
    ),
    # 10. local_traffic_activity — recent motor-vehicle observation near the parcel
    (
        "local_traffic_activity",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn,
            'local_traffic_activity',
            CASE WHEN ltc.volume >= 10000 THEN 0.04
                 WHEN ltc.volume >= 3000 THEN 0.02
                 ELSE 0.01 END,
            'staging.local_traffic_counts', ltc.globalid,
            ST_Distance(ST_Centroid(p.geom)::geography, ltc.geom::geography),
            jsonb_build_object(
                'counter_id', ltc.counter_id,
                'count_type', ltc.count_type,
                'purpose', ltc.purpose,
                'volume', ltc.volume,
                'count_year', ltc.count_year,
                'distance_m', ROUND(ST_Distance(ST_Centroid(p.geom)::geography, ltc.geom::geography)::numeric),
                'source_url', ltc.source_url
            )
        FROM staging.parcels p
        JOIN staging.local_traffic_counts ltc
            ON p.geom && ST_Expand(ltc.geom, %(local_traffic_radius_deg)s)
           AND ST_DWithin(
                ST_Centroid(p.geom)::geography,
                ltc.geom::geography,
                %(local_traffic_radius_m)s
            )
        WHERE p.valid_to IS NULL
          AND ltc.valid_to IS NULL
          AND ltc.volume > 0
          AND ltc.count_year >= EXTRACT(YEAR FROM NOW())::int - 5
          AND ltc.purpose IN ('HPMS', 'FUNCTIONAL CLASS', 'I-83 TAC REPORT', 'T & E STUDY', 'SPECIAL STUDY')
        ORDER BY
            p.pidn,
            ltc.count_year DESC,
            ST_Distance(ST_Centroid(p.geom)::geography, ltc.geom::geography)
        """,
    ),
    # 11. growth_area — PGA/SGA only, LOW WEIGHT (tiebreaker, not differentiator)
    (
        "growth_area",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'growth_area', 0.02,
            'staging.growth_areas', g.globalid, NULL,
            jsonb_build_object('ga_type', g.ga_type, 'ga_status', g.ga_status,
                               'basis', 'parcel_center',
                               'source_url', g.source_url)
        FROM staging.parcels p
        JOIN staging.growth_areas g
            ON ST_Intersects(ST_Centroid(p.geom), g.geom)
        WHERE p.valid_to IS NULL AND g.valid_to IS NULL
          AND g.ga_type IN ('PGA', 'SGA')
        ORDER BY p.pidn, g.ga_type
        """,
    ),
    # ── NEGATIVE / EXCLUSION SIGNALS ───────────────────────────────────
    # 12. soil_constraint — parcel-wide mapped slope, drainage, or runoff screen.
    #     A soil unit must cover at least 5% of the parcel to trigger the fixed
    #     site-screening penalty; all materially overlapping units are retained
    #     in evidence so the UI never mistakes one centroid unit for the parcel.
    (
        "soil_constraint",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        WITH soil_overlaps AS (
            SELECT p.pidn, s.*
            FROM staging.parcels p
            CROSS JOIN LATERAL public.parcel_soil_units(p.geom) s
            WHERE p.valid_to IS NULL AND p.geom IS NOT NULL
        ), soil_sources AS (
            SELECT o.pidn, ARRAY_AGG(DISTINCT source_id ORDER BY source_id) AS source_record_ids
            FROM soil_overlaps o CROSS JOIN LATERAL unnest(o.source_record_ids) source_id
            GROUP BY o.pidn
        )
        SELECT
            o.pidn,
            'soil_constraint',
            -0.08,
            'staging.soils',
            ARRAY_TO_STRING(src.source_record_ids, ','),
            NULL,
            jsonb_build_object(
                'screen_basis', 'parcel_overlap',
                'minimum_trigger_coverage_pct', 5,
                'source_record_ids', to_jsonb(src.source_record_ids),
                'soil_units', jsonb_agg(
                    jsonb_build_object(
                        'source_record_ids', to_jsonb(o.source_record_ids),
                        'map_unit_key', o.map_unit_key,
                        'map_unit_symbol', o.map_unit_symbol,
                        'map_unit_name', o.map_unit_name,
                        'coverage_pct', ROUND(o.coverage_pct, 1),
                        'drainage', o.drainage,
                        'septic_rating', o.septic_rating,
                        'slope_low', o.slope_low,
                        'slope_high', o.slope_high,
                        'representative_slope', o.representative_slope,
                        'hydric_rating', o.hydric_rating,
                        'hydrologic_group', o.hydrologic_group,
                        'constraint_reasons', to_jsonb(array_remove(ARRAY[
                            CASE WHEN COALESCE(o.representative_slope, 0) >= 15
                                 THEN 'steep_slope' END,
                            CASE WHEN o.drainage IN ('Poorly drained', 'Somewhat poorly drained')
                                 THEN 'poor_drainage' END,
                            CASE WHEN o.hydrologic_group = 'D'
                                 THEN 'high_runoff_potential' END
                        ], NULL))
                    ) ORDER BY o.coverage_pct DESC, o.source_record_ids
                ),
                'source_url', MIN(o.source_url)
            )
        FROM soil_overlaps o
        JOIN soil_sources src ON src.pidn = o.pidn
        WHERE o.coverage_pct > 0
        GROUP BY o.pidn, src.source_record_ids
        HAVING BOOL_OR(
            o.coverage_pct >= 5
            AND (
                COALESCE(o.representative_slope, 0) >= 15
                OR o.drainage IN ('Poorly drained', 'Somewhat poorly drained')
                OR o.hydrologic_group = 'D'
            )
        )
        """,
    ),
    # 13. zoning_constraint — special-purpose overlay requiring extra diligence
    (
        "zoning_constraint",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn,
            'zoning_constraint',
            CASE WHEN zo.overlay_type IN ('STEEP SLOPES', 'UNDERGROUND MINING')
                 THEN -0.08 ELSE -0.05 END,
            'staging.zoning_overlays', zo.globalid, NULL,
            jsonb_build_object(
                'overlay_type', zo.overlay_type,
                'overlay_name', zo.overlay_name,
                'description', zo.description,
                'municipality', zo.municipality,
                'basis', 'parcel_center',
                'source_url', zo.source_url
            )
        FROM staging.parcels p
        JOIN staging.zoning_overlays zo
            ON ST_Intersects(ST_Centroid(p.geom), zo.geom)
        WHERE p.valid_to IS NULL
          AND zo.valid_to IS NULL
          AND zo.overlay_type IN (
              'AIRPORT', 'HISTORIC', 'STEEP SLOPES',
              'UNDERGROUND MINING', 'WELLHEAD'
          )
        ORDER BY
            p.pidn,
            CASE WHEN zo.overlay_type IN ('STEEP SLOPES', 'UNDERGROUND MINING')
                 THEN 0 ELSE 1 END,
            zo.overlay_name
        """,
    ),
    # 14. environmental_diligence — a nearby public DEP record that warrants
    #     follow-up. This is screening evidence, never a contamination claim.
    (
        "environmental_diligence",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'environmental_diligence', -0.05,
            'staging.environmental_diligence_sites',
            eds.source_layer || ':' || eds.source_id,
            ST_Distance(ST_Centroid(p.geom)::geography, eds.geom::geography),
            jsonb_build_object(
                'screening_only', TRUE,
                'source_layer', eds.source_layer,
                'site_name', eds.site_name,
                'facility_type', eds.facility_type,
                'facility_status', eds.facility_status,
                'detail_url', eds.detail_url,
                'source_url', eds.source_url
            )
        FROM staging.parcels p
        JOIN staging.environmental_diligence_sites eds
            ON p.geom && ST_Expand(eds.geom, %(environmental_radius_deg)s)
           AND ST_DWithin(
                ST_Centroid(p.geom)::geography,
                eds.geom::geography,
                %(environmental_radius_m)s
            )
        WHERE p.valid_to IS NULL AND eds.valid_to IS NULL
        ORDER BY
            p.pidn,
            ST_Distance(ST_Centroid(p.geom)::geography, eds.geom::geography)
        """,
    ),
    # 15. flood_zone — SFHA flood zone (discount, not hard exclude)
    (
        "flood_zone",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        WITH flood_overlaps AS (
            SELECT
                p.pidn,
                f.fld_ar_id,
                f.fld_zone,
                f.zone_subty,
                f.source_url,
                ST_Intersection(ST_MakeValid(p.geom), ST_MakeValid(f.geom)) AS overlap_geom,
                ST_Area(ST_Transform(ST_MakeValid(p.geom), 32617)) AS parcel_area_m2
            FROM staging.parcels p
            JOIN staging.flood_zones f
              ON p.geom && f.geom
             AND ST_Intersects(p.geom, f.geom)
            WHERE p.valid_to IS NULL
              AND f.valid_to IS NULL
              AND p.geom IS NOT NULL
              AND f.geom IS NOT NULL
              AND f.sfha_tf = 'T'
        )
        SELECT
            o.pidn,
            'flood_zone',
            -0.10,
            'staging.flood_zones',
            STRING_AGG(DISTINCT o.fld_ar_id, ','),
            NULL,
            jsonb_build_object(
                'sfha_tf', 'T',
                'screen_basis', 'parcel_overlap',
                'minimum_trigger_coverage_pct', 1,
                'overlap_pct', ROUND((
                    100 * ST_Area(ST_Transform(ST_UnaryUnion(ST_Collect(o.overlap_geom)), 32617))
                    / NULLIF(MIN(o.parcel_area_m2), 0)
                )::numeric, 1),
                'flood_zones', jsonb_agg(DISTINCT jsonb_build_object(
                    'fld_zone', o.fld_zone,
                    'zone_subty', o.zone_subty
                )),
                'source_record_ids', jsonb_agg(DISTINCT o.fld_ar_id),
                'source_url', MIN(o.source_url)
            )
        FROM flood_overlaps o
        WHERE NOT ST_IsEmpty(o.overlap_geom)
        GROUP BY o.pidn
        HAVING (
            100 * ST_Area(ST_Transform(ST_UnaryUnion(ST_Collect(o.overlap_geom)), 32617))
            / NULLIF(MIN(o.parcel_area_m2), 0)
        ) >= 1
        """,
    ),
    # 15. conservation_easement — hard exclude
    #    Evidence includes preservation date, current owner, exclusion/federal
    #    flags, and district so Pass 2 can assess enforceability and scope.
    (
        "conservation_easement",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'conservation_easement', 0.00,
            'staging.conservation_easements', ce.ease_id, NULL,
            jsonb_build_object(
                'ease_id', ce.ease_id,
                'ease_code', ce.ease_code,
                'ease_acres', ce.ease_acres,
                'grantor', ce.grantor,
                'current_owner', ce.curr_owner,
                'preservation_date', ce.pres_date,
                'exclusion_flag', ce.exclusion,
                'federal_flag', ce.federal,
                'district', ce.district,
                'source_url', ce.source_url
            )
        FROM staging.parcels p
        JOIN staging.conservation_easements ce ON ce.pidn = p.pidn AND ce.valid_to IS NULL
        WHERE p.valid_to IS NULL
        ORDER BY p.pidn
        """,
    ),
    # 16. ag_security — planning context, not a development prohibition.
    #    Pennsylvania's official ASA guidance says enrollment does not restrict
    #    the landowner from selling, subdividing, or developing the property.
    (
        "ag_security",
        """
        INSERT INTO public.development_signals
            (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
        SELECT DISTINCT ON (p.pidn)
            p.pidn, 'ag_security', 0.00,
            'staging.ag_security', ag.resolution, NULL,
            jsonb_build_object(
                'resolution', ag.resolution,
                'res_acres', ag.res_acres,
                'res_date', ag.res_date,
                'last_review', ag.last_review,
                'book', ag.book,
                'page', ag.page,
                'instrument', ag.instrument,
                'flag', ag.flag,
                'district', ag.district,
                'development_prohibition', FALSE,
                'source_url', ag.source_url
            )
        FROM staging.parcels p
        JOIN staging.ag_security ag ON ag.pidn = p.pidn AND ag.valid_to IS NULL
        WHERE p.valid_to IS NULL
        ORDER BY p.pidn
        """,
    ),
]


def build_signal_params(county) -> dict:
    """Bind county thresholds; proximity radii also get a degree envelope.

    Every proximity join first narrows with ``geom && ST_Expand(...)`` so the
    GiST index on parcel geometry is used before the exact geography distance
    test. The envelope is deliberately generous (1 degree ≈ 85 km of longitude
    at 40° N, so 1 m ≈ 1.2e-5 degrees; we use 1.5e-5).
    """
    degrees_per_meter = 1.5e-5
    return {
        "subdivision_radius_m": county.signal_subdivision_radius_m,
        "subdivision_radius_deg": county.signal_subdivision_radius_m
        * degrees_per_meter,
        "subdivision_on_parcel_m": county.signal_subdivision_on_parcel_m,
        "subdivision_on_parcel_deg": county.signal_subdivision_on_parcel_m
        * degrees_per_meter,
        "infrastructure_radius_deg": county.signal_infrastructure_radius_m
        * degrees_per_meter,
        "local_traffic_radius_deg": county.signal_local_traffic_radius_m
        * degrees_per_meter,
        "environmental_radius_deg": county.signal_environmental_radius_m
        * degrees_per_meter,
        "business_owner_regex": BUSINESS_OWNER_REGEX,
        "infrastructure_radius_m": county.signal_infrastructure_radius_m,
        "local_traffic_radius_m": county.signal_local_traffic_radius_m,
        "environmental_radius_m": county.signal_environmental_radius_m,
        "nominal_sale_max": county.signal_nominal_sale_max,
        "vacancy_apr_max": county.signal_vacancy_apr_max,
        "vacancy_price_max": county.signal_vacancy_price_max,
        "assemblage_min_neighbors": county.signal_assemblage_min_neighbors,
        "assemblage_strong_neighbors": county.signal_assemblage_strong_neighbors,
    }


@asset(
    group_name="enrichment",
    deps=[
        "planning_subdivisions_arcgis",
        "business_parks_arcgis",
        "industrial_parks_arcgis",
        "zoning_overlays_arcgis",
        "soils_arcgis",
        "local_traffic_counts_arcgis",
        "growth_areas_arcgis",
        "future_landuse_arcgis",
        "conservation_easements_arcgis",
        "ag_security_arcgis",
        "parcels_arcgis",
        "penndot_projects_arcgis",
        "tax_claims",
        "fema_flood_zones",
        "pa_dep_environmental_diligence",
        "structures_arcgis",
        "zoning_arcgis",
        "proceeding_extraction",
        "municipal_evidence_linking",
    ],
    description="Spatial-join radar layers to parcels \u2192 public.development_signals",
    kinds={"postgres"},
)
def development_signals(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    """Compute privately, then publish signals and evidence retractions together."""

    county = get_county_config()
    source_keys = [county_open_data_source_key()]
    if county.penndot_projects_url:
        source_keys.append("penndot_open_data")
    if county.fema_nfhl_url and county.fema_dfirm_id:
        source_keys.append("fema_nfhl")
    if county.pa_dep_query_bbox:
        source_keys.append("pa_dep_open_data")
    authorize_source_uses(
        database,
        source_keys=tuple(source_keys),
        use="derived_product",
        asset_key="development_signals",
        dagster_run_id=context.run_id,
    )
    include_tax_claims = bool(county.tax_claims_pdf_url) and source_use_is_authorized(
        database,
        source_key="tax_claims",
        use="derived_product",
        asset_key="development_signals:tax_distress",
        dagster_run_id=context.run_id,
    )
    signal_params = build_signal_params(county)

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    signal_counts: dict[str, int] = {}
    total = 0

    try:
        # Serialize rebuilders before they acquire locks on the serving table.
        # Long spatial calculations must not hold TRUNCATE's read-blocking lock.
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtext('countyiq:development_signals'))"
        )
        cur.execute("""
            CREATE TEMP TABLE countyiq_new_signals ON COMMIT DROP AS
            SELECT pidn, signal_key, signal_weight, source_table, source_id,
                   distance_m, evidence
            FROM public.development_signals WITH NO DATA
        """)
        cur.execute("CREATE UNIQUE INDEX ON countyiq_new_signals (pidn, signal_key)")
        context.log.info(
            "Computing replacement signals while the current snapshot remains readable"
        )

        for signal_key, sql in _SIGNALS:
            if signal_key == "tax_distress" and not include_tax_claims:
                signal_counts[signal_key] = 0
                context.log.info(
                    "  tax_distress: disabled by county capability or source policy"
                )
                continue
            # These are code-owned SQL constants. Internal references (such as
            # nearby-plan exclusion) must also read this run's new signals.
            cur.execute(
                sql.replace(
                    "public.development_signals", "pg_temp.countyiq_new_signals"
                ),
                signal_params,
            )
            count = cur.rowcount
            signal_counts[signal_key] = count
            total += count
            context.log.info(f"  {signal_key}: {count:,} rows")

        # Publish source replacement and validation retraction atomically.
        # Waiting for the next paid-pass job leaves stale validations visible.
        # The pipeline has TRUNCATE/sequence USAGE, not sequence ownership.
        # Keep allocating IDs across snapshots; resetting them is unnecessary.
        cur.execute("TRUNCATE public.development_signals")
        cur.execute("""
            INSERT INTO public.development_signals
                (pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence)
            SELECT pidn, signal_key, signal_weight, source_table, source_id, distance_m, evidence
            FROM pg_temp.countyiq_new_signals
        """)
        cur.execute(
            RETRACT_STALE_EVIDENCE_QUERY, {"volatile": list(VOLATILE_EVIDENCE_KEYS)}
        )
        evidence_retracted = cur.rowcount
        conn.commit()
        context.log.info("Retracted %d stale validation rows", evidence_retracted)
        context.log.info(f"Committed {total:,} total signal rows")

    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    metadata = {
        "total_signal_rows": MetadataValue.int(total),
        "evidence_retracted": MetadataValue.int(evidence_retracted),
    }
    for key, count in signal_counts.items():
        metadata[key] = MetadataValue.int(count)
    return MaterializeResult(metadata=metadata)
