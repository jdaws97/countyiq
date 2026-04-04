-- ============================================================================
-- CountyIQ Model Evaluation Dataset
-- Extracts ~100 test parcels with diverse signal profiles for LLM eval.
--
-- Usage: Run each section independently to build your test set, or use
-- eval_runner.py which queries these categories programmatically.
-- ============================================================================


-- ============================================================================
-- Category A: High-signal parcels (3+ signals) — 50 parcels
-- Best for testing brief generation quality and signal synthesis.
-- ============================================================================
SELECT
    ds.pidn,
    COUNT(*)                                        AS signal_count,
    (
        SELECT ds2.signal_key
        FROM public.development_signals ds2
        WHERE ds2.pidn = ds.pidn
        ORDER BY ds2.signal_weight DESC
        LIMIT 1
    )                                               AS top_signal
FROM public.development_signals ds
GROUP BY ds.pidn
HAVING COUNT(*) >= 3
ORDER BY RANDOM()
LIMIT 50;


-- ============================================================================
-- Category B: Tax distress signals — 20 parcels
-- Tests the model's ability to assess financial risk context.
-- ============================================================================
SELECT
    ds.pidn,
    COUNT(*)                                        AS signal_count,
    ds.signal_key                                   AS top_signal
FROM public.development_signals ds
WHERE ds.signal_key = 'tax_distress'
GROUP BY ds.pidn, ds.signal_key
ORDER BY RANDOM()
LIMIT 20;


-- ============================================================================
-- Category C: Exclusion signals (conservation_easement, ag_security) — 10 parcels
-- Tests whether the model correctly treats these as hard constraints.
-- ============================================================================
SELECT
    ds.pidn,
    COUNT(*)                                        AS signal_count,
    ds.signal_key                                   AS top_signal
FROM public.development_signals ds
WHERE ds.signal_key IN ('conservation_easement', 'ag_security')
GROUP BY ds.pidn, ds.signal_key
ORDER BY RANDOM()
LIMIT 10;


-- ============================================================================
-- Category D: Assemblage signals — 20 parcels
-- Tests multi-parcel reasoning and entity resolution awareness.
-- ============================================================================
SELECT
    ds.pidn,
    COUNT(*)                                        AS signal_count,
    ds.signal_key                                   AS top_signal
FROM public.development_signals ds
WHERE ds.signal_key = 'assemblage'
GROUP BY ds.pidn, ds.signal_key
ORDER BY RANDOM()
LIMIT 20;


-- ============================================================================
-- Combined dataset query (used by eval_runner.py)
-- Returns up to 100 parcels across all four categories with a category label.
-- ============================================================================
WITH high_signal AS (
    SELECT
        ds.pidn,
        COUNT(*)                                    AS signal_count,
        (
            SELECT ds2.signal_key
            FROM public.development_signals ds2
            WHERE ds2.pidn = ds.pidn
            ORDER BY ds2.signal_weight DESC
            LIMIT 1
        )                                           AS top_signal,
        'high_signal'                               AS category
    FROM public.development_signals ds
    GROUP BY ds.pidn
    HAVING COUNT(*) >= 3
    ORDER BY RANDOM()
    LIMIT 50
),
tax_distress AS (
    SELECT
        ds.pidn,
        COUNT(*)                                    AS signal_count,
        ds.signal_key                               AS top_signal,
        'tax_distress'                              AS category
    FROM public.development_signals ds
    WHERE ds.signal_key = 'tax_distress'
      AND ds.pidn NOT IN (SELECT pidn FROM high_signal)
    GROUP BY ds.pidn, ds.signal_key
    ORDER BY RANDOM()
    LIMIT 20
),
exclusion AS (
    SELECT
        ds.pidn,
        COUNT(*)                                    AS signal_count,
        ds.signal_key                               AS top_signal,
        'exclusion'                                 AS category
    FROM public.development_signals ds
    WHERE ds.signal_key IN ('conservation_easement', 'ag_security')
      AND ds.pidn NOT IN (SELECT pidn FROM high_signal)
      AND ds.pidn NOT IN (SELECT pidn FROM tax_distress)
    GROUP BY ds.pidn, ds.signal_key
    ORDER BY RANDOM()
    LIMIT 10
),
assemblage AS (
    SELECT
        ds.pidn,
        COUNT(*)                                    AS signal_count,
        ds.signal_key                               AS top_signal,
        'assemblage'                                AS category
    FROM public.development_signals ds
    WHERE ds.signal_key = 'assemblage'
      AND ds.pidn NOT IN (SELECT pidn FROM high_signal)
      AND ds.pidn NOT IN (SELECT pidn FROM tax_distress)
      AND ds.pidn NOT IN (SELECT pidn FROM exclusion)
    GROUP BY ds.pidn, ds.signal_key
    ORDER BY RANDOM()
    LIMIT 20
)
SELECT * FROM high_signal
UNION ALL
SELECT * FROM tax_distress
UNION ALL
SELECT * FROM exclusion
UNION ALL
SELECT * FROM assemblage
ORDER BY category, pidn;
