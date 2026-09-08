"""Export, assess and explicitly review bounded emerging-intelligence packets.

Run from pipelines with .venv/bin/python scripts/emerging_intelligence.py --help.
Database target uses the standard DATABASE_* environment. Export and list are
read-only. Generation obeys the existing Pass 4 backend and execution budgets.
"""

import argparse
import json
import logging
from pathlib import Path

from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.emerging_intelligence import (
    ANALYSIS_SCHEMA,
    SYSTEM_PROMPT,
    generate_analysis,
)
from countyiq.lib.emerging_packets import DEFAULT_SETTINGS, build_packet, fetch_scope
from countyiq.lib.emerging_store import retain_analysis, review_analysis
from countyiq.lib.pass_llm_config import PassItemBudget, resolve_pass_harness
from countyiq.lib.pass_subscription import start_subscription_item
from countyiq.resources.database import make_database_resource


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser(
        "list", help="List current candidate scopes; no inference"
    )
    listing.add_argument("--limit", type=int, default=20)
    exporting = commands.add_parser(
        "export", help="Export one canonical evidence packet"
    )
    exporting.add_argument("--bundle", required=True)
    exporting.add_argument("--output", type=Path, required=True)
    exporting.add_argument(
        "--cutoff", help="Observed-date historical cutoff (ISO date/time)"
    )
    generating = commands.add_parser(
        "generate", help="Generate one draft using explicit Pass 4 configuration"
    )
    generating.add_argument("--packet", type=Path, required=True)
    generating.add_argument("--output", type=Path, required=True)
    importing = commands.add_parser(
        "import", help="Validate and retain an analysis; does not publish"
    )
    importing.add_argument("--packet", type=Path, required=True)
    importing.add_argument("--analysis", type=Path, required=True)
    importing.add_argument("--author", required=True)
    reviewing = commands.add_parser(
        "review",
        help="Record publication or withdrawal after reviewing sources and claims",
    )
    reviewing.add_argument("--inference-id", required=True, type=int)
    reviewing.add_argument("--action", required=True, choices=("publish", "withdraw"))
    reviewing.add_argument("--reviewer", required=True)
    reviewing.add_argument("--rationale", required=True)
    args = parser.parse_args()
    database = make_database_resource()
    database.setup_for_execution(None)
    if args.command == "list":
        if not 1 <= args.limit <= 100:
            parser.error("limit must be between 1 and 100")
        with database.read_snapshot() as cur:
            cur.execute(
                """SELECT bundle_key, latest_meeting_date, source->>'municipality' AS municipality,
                source->>'candidate_scope' AS candidate_scope
                FROM public.current_municipal_matter_sources
                ORDER BY latest_meeting_date DESC, bundle_key LIMIT %s""",
                (args.limit,),
            )
            print(
                json.dumps([dict(row) for row in cur.fetchall()], indent=2, default=str)
            )
    elif args.command == "export":
        settings = {
            **DEFAULT_SETTINGS,
            "open_data_key": county_open_data_source_key(get_county_config()),
        }
        with database.read_snapshot() as cur:
            packet = build_packet(
                fetch_scope(cur, args.bundle, settings), cutoff=args.cutoff
            )
        args.output.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n")
    elif args.command == "generate":
        packet = json.loads(args.packet.read_text())
        from countyiq.lib.emerging_packets import verify_packet

        with database.read_snapshot() as cur:
            verify_packet(cur, packet)
        logger = logging.getLogger("emerging_intelligence")
        config, invoke = resolve_pass_harness(
            logger,
            pass_number=4,
            archive_label="emerging_intelligence",
            default_max_tokens=12000,
            json_schema=ANALYSIS_SCHEMA,
            schema_name="emerging_analysis",
            system_prompt=SYSTEM_PROMPT,
        )
        if not PassItemBudget(4).claim(logger, label="emerging intelligence"):
            raise ValueError("Pass 4 item budget does not permit this analysis")
        start_subscription_item(invoke)
        analysis, _ = generate_analysis(packet, config, invoke)
        args.output.write_text(
            json.dumps(analysis, indent=2, ensure_ascii=False) + "\n"
        )
        print(
            "Draft written. Review and import it before an explicit publication review."
        )
    elif args.command == "import":
        result = retain_analysis(
            database,
            json.loads(args.packet.read_text()),
            json.loads(args.analysis.read_text()),
            author=args.author,
        )
        print(
            json.dumps(
                {
                    "inference_id": result.inference_id,
                    "accepted": result.accepted,
                    "reason": result.reason,
                }
            )
        )
    else:
        review_id = review_analysis(
            database,
            args.inference_id,
            action=args.action,
            reviewer=args.reviewer,
            rationale=args.rationale,
        )
        print(json.dumps({"publication_id": review_id, "action": args.action}))


if __name__ == "__main__":
    main()
