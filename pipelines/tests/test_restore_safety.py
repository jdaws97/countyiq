"""Regression checks for cross-pair restore database collisions."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "names,valid",
    [
        (
            ("countyiq", "dagster", "countyiq_restore_drill", "dagster_restore_drill"),
            True,
        ),
        (
            (
                "countyiq",
                "countyiq_restore_drill",
                "countyiq_restore_drill",
                "countyiq_restore_drill_restore_drill",
            ),
            False,
        ),
        (
            (
                "dagster_restore_drill",
                "dagster",
                "dagster_restore_drill_restore_drill",
                "dagster_restore_drill",
            ),
            False,
        ),
        (
            (
                "countyiq",
                "countyiq",
                "countyiq_restore_drill",
                "countyiq_restore_drill",
            ),
            False,
        ),
        (("countyiq", "dagster", "countyiq", "dagster_restore_drill"), False),
        (("countyiq", "dagster", "bad;name", "dagster_restore_drill"), False),
    ],
)
def test_restore_targets_are_safe_across_all_database_pairs(names, valid):
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source docker/lib/operations.sh; countyiq_validate_restore_targets "$@"',
            "restore-test",
            *names,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is valid, result.stderr
