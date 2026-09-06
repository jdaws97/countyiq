"""Back-test radar signals against historical subdivision / land-development plans.

The county publishes every subdivision and land-development plan it has
received, with a received date and a point location. That is a real outcome
label: "a believable plan was filed on this parcel". This script asks which
deterministic radar signals predicted that outcome, so opportunity weights can
be set from evidence instead of by hand. It makes no model calls.

Method
------
1. Rebuild every deterministic signal from ``development_signals._SIGNALS``
   into a TEMP table (the production queries, unchanged, retargeted).
   Plan-derived signals (``active_subdivision``, ``nearby_subdivision``) are
   excluded because they are the label.
2. Label each eligible parcel:
   - positive: a believable plan point (prop_du > 0 or land development)
     received in the last ``--label-months`` sits on the parcel
     (within ``--on-parcel-m``);
   - ambiguous (dropped from the fit): an older believable plan within the
     corridor radius, so stale activity does not pollute the negatives;
   - negative: everything else.
   Parcels with a conservation easement or agricultural-security enrollment
   are excluded, exactly as the radar excludes them.
3. Group parcels by their binary signal pattern and fit a ridge logistic
   regression with iteratively reweighted least squares (pure Python; the
   pipeline environment has no numpy).
4. Report per-signal lift, weight of evidence, fitted coefficients, AUC and
   precision@K for the current weights versus the fitted weights, and the
   proposed rounded opportunity weights plus score quantiles for UI thresholds.

Leakage caveats (also written to the report): the signals are computed on the
current snapshot, not the state before the plan. ``ownership_change`` is only
counted for positives when the sale predates the plan. ``vacancy`` is likely
under-counted for positives because built-out plans now have structures. The
fitted weights are a defensible starting point, not a causal claim.

Usage (from ``pipelines``)::

    .venv/bin/python scripts/backtest_radar_weights.py \
        --output-json ../docs/research/radar-backtest-2026-09-02.json \
        --output-md ../docs/research/radar-backtest-2026-09-02.md
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from countyiq.assets.enrichment.development_signals import (
    _SIGNALS,
    build_signal_params,
)
from countyiq.lib.county_config import get_county_config

LABEL_SIGNAL_KEYS = {"active_subdivision", "nearby_subdivision"}
EXCLUSION_KEYS = {"conservation_easement"}
CONTEXT_ONLY_KEYS = {"ag_security"}
RISK_KEYS = {
    "flood_zone",
    "soil_constraint",
    "zoning_constraint",
    "environmental_diligence",
}

# Current (score_version 5) opportunity weights, reconstructed from the
# signal weights and the v5 formula so precision@K has a baseline.
CURRENT_OPPORTUNITY_WEIGHTS = {
    "economic_development_park": 0.16,
    "ownership_change": 0.10,
    "tax_distress": 0.10,
    "vacancy": 0.12,
    "assemblage": 0.08,
    "zoning_mismatch": 0.10,
    "penndot_project": 0.03,
    "development_overlay": 0.04,
    "local_traffic_activity": 0.03,
    "growth_area": 0.02,
    "flood_zone": -0.10,
    "soil_constraint": -0.08,
    "zoning_constraint": -0.06,
    "environmental_diligence": -0.05,
}


def _connect():
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", "5433")),
        dbname=os.environ.get("DATABASE_NAME", "countyiq"),
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )


def _signal_params(county) -> dict:
    return build_signal_params(county)


def build_signals(cur, params: dict, log) -> dict[str, int]:
    cur.execute(
        "CREATE TEMP TABLE backtest_signals "
        "(LIKE public.development_signals INCLUDING DEFAULTS)"
    )
    counts: dict[str, int] = {}
    for key, sql in _SIGNALS:
        if key in LABEL_SIGNAL_KEYS:
            continue
        started = time.monotonic()
        cur.execute(
            sql.replace("public.development_signals", "backtest_signals"), params
        )
        counts[key] = cur.rowcount
        log(f"  {key}: {cur.rowcount:,} rows ({time.monotonic() - started:.1f}s)")
    cur.execute("CREATE INDEX ON backtest_signals (pidn, signal_key)")
    return counts


def build_labels(
    cur, *, label_months: int, on_parcel_m: int, corridor_m: int, clean_years: int, log
):
    started = time.monotonic()
    # Eligible parcels go into an indexed temp table. A multiply-referenced
    # CTE would be materialised without an index, turning each spatial join
    # into a full nested loop over 176k parcels.
    cur.execute(
        """
        CREATE TEMP TABLE backtest_eligible AS
        SELECT p.pidn, p.geom, p.class
        FROM staging.parcels p
        WHERE p.valid_to IS NULL
          AND p.geom IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM backtest_signals x
              WHERE x.pidn = p.pidn
                AND x.signal_key = 'conservation_easement'
          )
        """
    )
    cur.execute("CREATE INDEX ON backtest_eligible USING GIST (geom)")
    cur.execute("CREATE INDEX ON backtest_eligible (pidn)")
    cur.execute(
        """
        CREATE TEMP TABLE backtest_believable AS
        SELECT geom, date_rcvd
        FROM staging.planning_subdivisions
        WHERE valid_to IS NULL
          AND date_rcvd IS NOT NULL
          AND (COALESCE(prop_du, 0) > 0 OR UPPER(COALESCE(pt_land_dev, 'NO')) = 'YES')
        """
    )
    cur.execute("ANALYZE backtest_eligible")
    cur.execute("ANALYZE backtest_believable")
    cur.execute(
        """
        CREATE TEMP TABLE backtest_positives AS
        SELECT e.pidn, MIN(b.date_rcvd) AS plan_date
        FROM backtest_believable b
        JOIN backtest_eligible e
          ON e.geom && ST_Expand(b.geom, %(on_parcel_deg)s)
         AND ST_DWithin(e.geom::geography, b.geom::geography, %(on_parcel_m)s)
        WHERE b.date_rcvd >= NOW() - (%(label_months)s || ' months')::interval
          AND b.date_rcvd <= NOW()
        GROUP BY e.pidn
        """,
        {
            "on_parcel_m": on_parcel_m,
            "on_parcel_deg": on_parcel_m * 1.5e-5,
            "label_months": label_months,
        },
    )
    cur.execute("CREATE INDEX ON backtest_positives (pidn)")
    cur.execute(
        """
        CREATE TEMP TABLE backtest_stale AS
        SELECT DISTINCT e.pidn
        FROM backtest_believable b
        JOIN backtest_eligible e
          ON e.geom && ST_Expand(b.geom, %(corridor_deg)s)
         AND ST_DWithin(e.geom::geography, b.geom::geography, %(corridor_m)s)
        WHERE b.date_rcvd >= NOW() - (%(clean_years)s || ' years')::interval
          AND b.date_rcvd < NOW() - (%(label_months)s || ' months')::interval
        """,
        {
            "corridor_m": corridor_m,
            "corridor_deg": corridor_m * 1.5e-5,
            "clean_years": clean_years,
            "label_months": label_months,
        },
    )
    cur.execute("CREATE INDEX ON backtest_stale (pidn)")
    cur.execute(
        """
        CREATE TEMP TABLE backtest_labels AS
        SELECT
            e.pidn,
            e.class,
            (pos.pidn IS NOT NULL) AS positive,
            pos.plan_date,
            (pos.pidn IS NULL AND sn.pidn IS NOT NULL) AS ambiguous
        FROM backtest_eligible e
        LEFT JOIN backtest_positives pos ON pos.pidn = e.pidn
        LEFT JOIN backtest_stale sn ON sn.pidn = e.pidn
        """
    )
    cur.execute("CREATE INDEX ON backtest_labels (pidn)")
    cur.execute(
        """
        SELECT
            COUNT(*) AS eligible,
            COUNT(*) FILTER (WHERE positive) AS positives,
            COUNT(*) FILTER (WHERE ambiguous) AS ambiguous
        FROM backtest_labels
        """
    )
    row = cur.fetchone()
    log(
        f"  labels: eligible={row['eligible']:,} positives={row['positives']:,} "
        f"ambiguous={row['ambiguous']:,} ({time.monotonic() - started:.1f}s)"
    )
    return dict(row)


def fetch_patterns(
    cur, feature_keys: list[str]
) -> list[tuple[tuple[int, ...], int, int]]:
    """Return grouped rows: (pattern, positives, total) for the fit population."""
    columns = []
    for key in feature_keys:
        if key == "ownership_change":
            # Leakage guard: for positives the sale must predate the plan.
            columns.append(
                """
                BOOL_OR(s.signal_key = 'ownership_change'
                        AND (NOT l.positive
                             OR to_date(s.evidence->>'saledt', 'DD-MON-YYYY') < l.plan_date))
                """
            )
        else:
            columns.append(f"BOOL_OR(s.signal_key = '{key}')")
    select_features = ",\n            ".join(
        f"COALESCE(({expr}), FALSE)::int AS f{i}" for i, expr in enumerate(columns)
    )
    pattern_cols = ", ".join(f"f{i}" for i in range(len(columns)))
    cur.execute(
        f"""
        WITH per_parcel AS (
            SELECT
                l.pidn,
                l.positive,
                {select_features}
            FROM backtest_labels l
            LEFT JOIN backtest_signals s ON s.pidn = l.pidn
            WHERE NOT l.ambiguous
            GROUP BY l.pidn, l.positive, l.plan_date
        )
        SELECT {pattern_cols},
               COUNT(*) FILTER (WHERE positive) AS positives,
               COUNT(*) AS total
        FROM per_parcel
        GROUP BY {pattern_cols}
        """
    )
    rows = []
    for row in cur.fetchall():
        pattern = tuple(int(row[f"f{i}"]) for i in range(len(columns)))
        rows.append((pattern, int(row["positives"]), int(row["total"])))
    return rows


# --------------------------------------------------------------------------
# Pure-Python statistics
# --------------------------------------------------------------------------


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    a = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        a[col], a[pivot] = a[pivot], a[col]
        if abs(a[col][col]) < 1e-12:
            raise ValueError("singular system")
        for r in range(n):
            if r == col:
                continue
            factor = a[r][col] / a[col][col]
            if factor:
                for c in range(col, n + 1):
                    a[r][c] -= factor * a[col][c]
    return [a[i][n] / a[i][i] for i in range(n)]


def _deviance(rows, beta: list[float], ridge: float) -> float:
    total = 0.0
    for x, pos, tot in rows:
        eta = max(min(sum(b * xi for b, xi in zip(beta, x)), 30.0), -30.0)
        # -2 * binomial log-likelihood (up to a constant)
        total += 2.0 * (tot * math.log1p(math.exp(eta)) - pos * eta)
    total += ridge * sum(b * b for b in beta[1:])
    return total


def fit_logistic(
    patterns: list[tuple[tuple[int, ...], int, int]],
    n_features: int,
    *,
    ridge: float,
    max_iter: int = 60,
) -> list[float]:
    """Ridge logistic regression by damped IRLS on grouped binomial data.

    Returns [intercept, coef_1, ..., coef_k]. The ridge penalty is not
    applied to the intercept. Each Newton step is halved until the penalised
    deviance decreases, which keeps sparse or near-separable signals (a
    signal with zero positives, for example) from throwing the fit to
    absurd magnitudes.
    """
    k = n_features + 1
    beta = [0.0] * k
    total_pos = sum(p for _, p, _ in patterns)
    total = sum(t for _, _, t in patterns)
    if 0 < total_pos < total:
        beta[0] = math.log(total_pos / (total - total_pos))
    rows = [((1,) + pattern, pos, tot) for pattern, pos, tot in patterns]
    current = _deviance(rows, beta, ridge)
    for _ in range(max_iter):
        hessian = [[0.0] * k for _ in range(k)]
        gradient = [0.0] * k
        for x, pos, tot in rows:
            eta = max(min(sum(b * xi for b, xi in zip(beta, x)), 30.0), -30.0)
            mu = 1.0 / (1.0 + math.exp(-eta))
            w = tot * mu * (1.0 - mu)
            resid = pos - tot * mu
            for i in range(k):
                if not x[i]:
                    continue
                gradient[i] += resid
                for j in range(k):
                    if x[j]:
                        hessian[i][j] += w
        for i in range(1, k):
            gradient[i] -= ridge * beta[i]
            hessian[i][i] += ridge
        step = _solve(hessian, gradient)
        scale = 1.0
        improved = False
        for _halving in range(20):
            candidate = [b + scale * st for b, st in zip(beta, step)]
            candidate_dev = _deviance(rows, candidate, ridge)
            if candidate_dev <= current + 1e-9:
                beta = candidate
                improved = candidate_dev < current - 1e-9
                current = candidate_dev
                break
            scale *= 0.5
        else:
            break
        if not improved or max(abs(scale * st) for st in step) < 1e-7:
            break
    return beta


def auc_from_patterns(scored: list[tuple[float, int, int]]) -> float:
    """scored: (score, positives, total). Mann-Whitney AUC with tie handling."""
    total_pos = sum(p for _, p, _ in scored)
    total_neg = sum(t - p for _, p, t in scored)
    if not total_pos or not total_neg:
        return float("nan")
    ordered = sorted(scored, key=lambda item: item[0])
    auc = 0.0
    neg_below = 0
    i = 0
    while i < len(ordered):
        j = i
        pos_here = 0
        neg_here = 0
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            pos_here += ordered[j][1]
            neg_here += ordered[j][2] - ordered[j][1]
            j += 1
        auc += pos_here * (neg_below + 0.5 * neg_here)
        neg_below += neg_here
        i = j
    return auc / (total_pos * total_neg)


def precision_at_k(scored: list[tuple[float, int, int]], k: int) -> float:
    ordered = sorted(scored, key=lambda item: -item[0])
    taken = 0
    hits = 0.0
    for score, pos, tot in ordered:
        if taken >= k:
            break
        take = min(tot, k - taken)
        hits += pos * (take / tot)
        taken += take
    return hits / max(taken, 1)


def score_quantiles(
    scored: list[tuple[float, int, int]], quantiles: list[float]
) -> dict[str, float]:
    ordered = sorted(scored, key=lambda item: -item[0])
    total = sum(t for _, _, t in ordered)
    result = {}
    for q in quantiles:
        target = q * total
        seen = 0
        value = ordered[-1][0] if ordered else 0.0
        for score, _, tot in ordered:
            seen += tot
            if seen >= target:
                value = score
                break
        result[f"top_{q:.3%}"] = value
    return result


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def propose_weights(feature_keys: list[str], coefs: list[float]) -> dict[str, float]:
    """Scale coefficients to opportunity weights on a 0–1 raw scale.

    Positive coefficients are normalised so the three strongest predictors
    sum to 0.60, which keeps a two-signal parcel in the 30–45 band the UI
    already treats as "recommended". Risk signals are clipped to be
    non-positive and every other signal to be non-negative so a weight never
    contradicts its product meaning.
    """
    pos = sorted((c for c in coefs if c > 0), reverse=True)[:3]
    scale = 0.60 / sum(pos) if pos else 1.0
    weights: dict[str, float] = {}
    for key, coef in zip(feature_keys, coefs):
        weight = round(coef * scale, 2)
        if key in RISK_KEYS:
            weight = min(weight, 0.0)
        else:
            weight = max(weight, 0.0)
        weights[key] = weight
    return weights


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        f"# Radar opportunity back-test ({report['generated_at'][:10]})",
        "",
        (
            "Deterministic back-test of radar signals against believable subdivision "
            "and land-development plans received on the parcel. No model calls."
        ),
        "",
        "## Population",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for key, value in report["population"].items():
        lines.append(f"| {key} | {value:,} |")
    lines += [
        "",
        (
            f"Label window: plans received in the last {report['parameters']['label_months']} months "
            f"within {report['parameters']['on_parcel_m']} m of the parcel. Parcels with an older "
            f"believable plan within {report['parameters']['corridor_m']} m in the last "
            f"{report['parameters']['clean_years']} years are excluded from the fit as ambiguous."
        ),
        "",
        "## Per-signal evidence",
        "",
        "| Signal | Parcels with signal | Positive rate with | Positive rate without | Lift | WoE | Coefficient | Proposed weight | Current weight |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["signals"]:
        lines.append(
            f"| {row['key']} | {row['n_with']:,} | {row['rate_with']:.3%} | "
            f"{row['rate_without']:.3%} | {row['lift']:.2f} | {row['woe']:+.2f} | "
            f"{row['coefficient']:+.3f} | {row['proposed_weight']:+.2f} | "
            f"{row['current_weight']:+.2f} |"
        )
    lines += [
        "",
        f"Intercept: {report['intercept']:+.3f} (ridge λ={report['parameters']['ridge']}).",
        "",
        "## Ranking quality",
        "",
        "| Scorer | AUC | " + " | ".join(f"P@{k}" for k in report["top_k"]) + " |",
        "|---|---|" + "---|" * len(report["top_k"]),
    ]
    for name, metrics in report["ranking"].items():
        cells = " | ".join(
            f"{metrics['precision_at'][str(k)]:.3%}" for k in report["top_k"]
        )
        lines.append(f"| {name} | {metrics['auc']:.4f} | {cells} |")
    lines += [
        "",
        f"Base positive rate: {report['base_rate']:.3%}.",
        "",
        "## Proposed opportunity score quantiles (raw × 100)",
        "",
        "| Quantile | Score |",
        "|---|---|",
    ]
    for key, value in report["proposed_score_quantiles"].items():
        lines.append(f"| {key} | {value * 100:.0f} |")
    lines += [
        "",
        "## Caveats",
        "",
    ]
    for caveat in report["caveats"]:
        lines.append(f"- {caveat}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--label-months", type=int, default=24)
    parser.add_argument("--on-parcel-m", type=int, default=None)
    parser.add_argument("--corridor-m", type=int, default=None)
    parser.add_argument("--clean-years", type=int, default=10)
    parser.add_argument("--ridge", type=float, default=2.0)
    parser.add_argument("--top-k", type=int, nargs="*", default=[250, 1000, 5000])
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    args = parser.parse_args()

    def log(message: str) -> None:
        print(message, flush=True)

    county = get_county_config()
    params = _signal_params(county)
    on_parcel_m = args.on_parcel_m or county.signal_subdivision_on_parcel_m
    corridor_m = args.corridor_m or county.signal_subdivision_radius_m

    conn = _connect()
    conn.autocommit = False
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        log("Building signals into a temporary table")
        signal_counts = build_signals(cur, params, log)
        log("Building labels")
        population = build_labels(
            cur,
            label_months=args.label_months,
            on_parcel_m=on_parcel_m,
            corridor_m=corridor_m,
            clean_years=args.clean_years,
            log=log,
        )
        feature_keys = [
            key
            for key, _ in _SIGNALS
            if key not in LABEL_SIGNAL_KEYS
            and key not in EXCLUSION_KEYS
            and key not in CONTEXT_ONLY_KEYS
        ]
        log("Grouping parcels by signal pattern")
        patterns = fetch_patterns(cur, feature_keys)
    finally:
        conn.rollback()
        conn.close()

    total = sum(t for _, _, t in patterns)
    total_pos = sum(p for _, p, _ in patterns)
    base_rate = total_pos / total if total else 0.0
    log(
        f"  {len(patterns):,} distinct patterns over {total:,} parcels ({total_pos:,} positives)"
    )

    log("Fitting ridge logistic regression")
    beta = fit_logistic(patterns, len(feature_keys), ridge=args.ridge)
    coefs = beta[1:]
    proposed = propose_weights(feature_keys, coefs)

    def pattern_score(weights: dict[str, float], pattern: tuple[int, ...]) -> float:
        return sum(weights.get(key, 0.0) * x for key, x in zip(feature_keys, pattern))

    fitted_scored = [
        (sum(c * x for c, x in zip(coefs, pattern)), pos, tot)
        for pattern, pos, tot in patterns
    ]
    proposed_scored = [
        (pattern_score(proposed, pattern), pos, tot) for pattern, pos, tot in patterns
    ]
    current_scored = [
        (pattern_score(CURRENT_OPPORTUNITY_WEIGHTS, pattern), pos, tot)
        for pattern, pos, tot in patterns
    ]
    ranking = {}
    for name, scored in (
        ("current_v5_weights", current_scored),
        ("fitted_logistic", fitted_scored),
        ("proposed_v6_weights", proposed_scored),
    ):
        ranking[name] = {
            "auc": auc_from_patterns(scored),
            "precision_at": {str(k): precision_at_k(scored, k) for k in args.top_k},
        }

    signals_report = []
    for idx, key in enumerate(feature_keys):
        n_with = sum(t for pattern, _, t in patterns if pattern[idx])
        pos_with = sum(p for pattern, p, _ in patterns if pattern[idx])
        n_without = total - n_with
        pos_without = total_pos - pos_with
        rate_with = pos_with / n_with if n_with else 0.0
        rate_without = pos_without / n_without if n_without else 0.0
        p_x_pos = (pos_with + 0.5) / (total_pos + 1)
        p_x_neg = (n_with - pos_with + 0.5) / (total - total_pos + 1)
        signals_report.append(
            {
                "key": key,
                "n_with": n_with,
                "positives_with": pos_with,
                "rate_with": rate_with,
                "rate_without": rate_without,
                "lift": (rate_with / base_rate) if base_rate else 0.0,
                "woe": math.log(p_x_pos / p_x_neg),
                "coefficient": coefs[idx],
                "proposed_weight": proposed[key],
                "current_weight": CURRENT_OPPORTUNITY_WEIGHTS.get(key, 0.0),
            }
        )
    signals_report.sort(key=lambda row: -row["coefficient"])

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "county": county.key
        if hasattr(county, "key")
        else os.environ.get("COUNTY", "york"),
        "parameters": {
            "label_months": args.label_months,
            "on_parcel_m": on_parcel_m,
            "corridor_m": corridor_m,
            "clean_years": args.clean_years,
            "ridge": args.ridge,
        },
        "population": {
            "eligible_parcels": population["eligible"],
            "positives": population["positives"],
            "ambiguous_excluded": population["ambiguous"],
            "fit_parcels": total,
            "distinct_patterns": len(patterns),
        },
        "signal_counts": signal_counts,
        "base_rate": base_rate,
        "intercept": beta[0],
        "signals": signals_report,
        "proposed_weights": proposed,
        "ranking": ranking,
        "top_k": args.top_k,
        "proposed_score_quantiles": score_quantiles(
            proposed_scored, [0.001, 0.005, 0.01, 0.02, 0.05, 0.10]
        ),
        "caveats": [
            (
                "Signals are computed on the current snapshot, not the parcel state "
                "before the plan was filed."
            ),
            (
                "ownership_change counts for positives only when the sale predates the "
                "plan; other signals have no such guard."
            ),
            (
                "vacancy is likely under-counted for positives because built-out plans "
                "now carry structures, so its coefficient is conservative."
            ),
            (
                "municipal_action and entity_assemblage depend on Pass 0 extractions and "
                "recent-sale data; with few rows their coefficients are dominated by the "
                "ridge prior."
            ),
            "Precision@K is computed with fractional credit inside tied score groups.",
            "This is predictive evidence for ranking, not a causal or entitlement claim.",
        ],
    }

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        log(f"Wrote {args.output_json}")
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(args.output_md, report)
        log(f"Wrote {args.output_md}")

    log("")
    log("Proposed opportunity weights:")
    for row in signals_report:
        log(
            f"  {row['key']:28s} coef={row['coefficient']:+.3f} lift={row['lift']:.2f} -> {row['proposed_weight']:+.2f}"
        )
    for name, metrics in ranking.items():
        log(
            f"  {name:22s} AUC={metrics['auc']:.4f} "
            + " ".join(
                f"P@{k}={metrics['precision_at'][str(k)]:.3%}" for k in args.top_k
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
