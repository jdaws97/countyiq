"""Record an explicit source review for cross-document candidate retrieval."""

import argparse
import json
import sys
from pathlib import Path

from countyiq.lib.municipal_candidate_review import review_candidate_group
from countyiq.resources.database import make_database_resource


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", help="Review JSON path, or - for standard input")
    args = parser.parse_args()
    text = sys.stdin.read() if args.packet == "-" else Path(args.packet).read_text()
    packet = json.loads(text)
    database = make_database_resource()
    database.setup_for_execution(None)
    try:
        print(json.dumps(review_candidate_group(database, **packet)))
    finally:
        database.teardown_after_execution(None)


if __name__ == "__main__":
    main()
