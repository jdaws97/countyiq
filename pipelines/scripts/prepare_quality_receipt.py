"""Print an unapproved receipt template; never claims an evaluation was run."""

import argparse
import json
from countyiq.lib.quality_release import release_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass-number", type=int, choices=range(4), required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "identity": release_identity(args.pass_number),
                "decision": "pending",
                "reviewer": "",
                "reviewed_at": "",
                "evaluation_record": {"path": "", "sha256": ""},
                "catastrophic_errors": None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
