"""Estimate CountyIQ LLM backfill volume and cost without making model calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from countyiq.lib.backfill_estimator import estimate_backfill
from countyiq.resources.database import make_database_resource


def _range(minimum: int, maximum: int) -> str:
    return f"{minimum:,}" if minimum == maximum else f"{minimum:,}-{maximum:,}"


def _money(minimum: float | None, maximum: float | None) -> str:
    if minimum is None or maximum is None:
        return "unknown"
    if minimum == maximum:
        return f"${maximum:,.4f}"
    return f"${minimum:,.4f}-${maximum:,.4f}"


def render_report(report: dict) -> str:
    headers = (
        "Pass",
        "Runtime",
        "Units",
        "Planning calls",
        "Planning cost",
        "Retry ceiling",
    )
    rows = []
    for item in report["passes"]:
        rows.append((
            item["key"],
            "enabled" if item["enabled_in_environment"] else "disabled",
            _range(item["units_min"], item["units_max"]),
            _range(item["planning_calls_min"], item["planning_calls_max"]),
            _money(item["planning_cost_min"], item["planning_cost_max"]),
            (
                f"{item['retry_ceiling_calls']:,} / "
                f"{_money(item['retry_ceiling_cost'], item['retry_ceiling_cost'])}"
            ),
        ))

    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    lines = [
        "  ".join(headers[index].ljust(widths[index]) for index in range(len(headers))),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(row[index].ljust(widths[index]) for index in range(len(headers)))
        for row in rows
    )
    totals = report["totals"]
    profile = report["data_profile"]
    counts = profile["counts"]
    lines.extend([
        "",
        (
            "Input snapshot: "
            f"{counts['parcels']:,} parcels, "
            f"{counts['proceedings']:,} proceedings, "
            f"{counts['corporate_entities']:,} corporate rows, "
            f"{counts['development_signals']:,} development signals, "
            f"{counts['owners']:,} owners"
        ),
        f"Planning total: {_range(totals['planning_calls_min'], totals['planning_calls_max'])} calls, "
        f"{_money(totals['planning_cost_min'], totals['planning_cost_max'])}",
        f"Retry/output ceiling: {totals['retry_ceiling_calls']:,} calls, "
        f"{_money(totals['retry_ceiling_cost'], totals['retry_ceiling_cost'])}",
        "Pass 4 is excluded because it is disabled and not required by the alpha product.",
        "Runtime gates are status only: planning cost models the hypothetical backfill before enablement.",
        "Costs use visible output-token assumptions and no-cache pricing; inspect JSON for caveats.",
    ])
    lines.extend(f"WARNING: {warning}" for warning in profile["warnings"])
    pass0 = report["passes"][0]
    pass0_details = pass0["details"]
    lines.extend([
        (
            "Pass 0 recent-window scenarios: "
            f"365 days {pass0_details['last_365_days_planning_calls']:,} calls / "
            f"{_money(pass0_details['last_365_days_planning_cost'], pass0_details['last_365_days_planning_cost'])}; "
            f"730 days {pass0_details['last_730_days_planning_calls']:,} calls / "
            f"{_money(pass0_details['last_730_days_planning_cost'], pass0_details['last_730_days_planning_cost'])}"
        )
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Maximum production-shaped prompts sampled per pass (default: 50)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full machine-readable report instead of the summary table",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the full JSON report",
    )
    args = parser.parse_args()

    if args.sample_size < 1:
        parser.error("--sample-size must be at least 1 so cost is not understated")

    database = make_database_resource()
    database.setup_for_execution(None)
    try:
        # Defense in depth: even an accidental future write in a reused helper
        # fails at PostgreSQL instead of mutating the backfill database.
        database.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        try:
            report = estimate_backfill(database, sample_size=args.sample_size)
        except RuntimeError as exc:
            parser.exit(2, f"estimate unavailable: {exc}\n")
    finally:
        database.teardown_after_execution(None)

    serialized = json.dumps(report, indent=2, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")

    print(serialized if args.json else render_report(report), end="")
    if args.output and not args.json:
        print(f"\nFull report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
