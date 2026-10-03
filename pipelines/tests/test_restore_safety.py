"""Keep disposable restore targets separate from the primary database."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "names,valid",
    [
        (("countyiq", "countyiq_restore_drill"), True),
        (("countyiq", "countyiq"), False),
        (("countyiq", "bad;name"), False),
        (("bad;name", "countyiq_restore_drill"), False),
        (("countyiq", "a" * 64), False),
        (("countyiq", ""), False),
    ],
)
def test_restore_target_is_valid_and_distinct_from_primary(names, valid):
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
        check=False,
    )
    assert (result.returncode == 0) is valid, result.stderr
