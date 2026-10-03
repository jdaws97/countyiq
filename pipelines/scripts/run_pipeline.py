"""Run CountyIQ locally, with an optional protected connection to the VPS.

Example: python scripts/run_pipeline.py --ssh-target ubuntu@host
--identity-file ~/.ssh/key --job arcgis_refresh --assets traffic_counts_arcgis
"""

from __future__ import annotations

import argparse
import fcntl
import os
import shutil
import sys
from pathlib import Path

from countyiq.lib.remote_pipeline import PipelineSession, run_command

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = {
    "subscription-backfill": "subscription_backfill.py",
    "rebind-subscription": "rebind_subscription_reads.py",
    "intelligence-preflight": "verify_intelligence_preflight.py",
    "estimate-backfill": "estimate_llm_backfill.py",
    "emerging-intelligence": "emerging_intelligence.py",
}


def prepare_state(directory: Path) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        raise ValueError("Pipeline state must be a directory owned by the current user")
    directory.chmod(0o700)
    home = directory / "dagster"
    home.mkdir(exist_ok=True, mode=0o700)
    expected = ROOT / "pipelines/dagster.yaml"
    configuration = home / "dagster.yaml"
    if configuration.exists() and configuration.read_bytes() != expected.read_bytes():
        raise ValueError("Local Dagster configuration differs from this release")
    if not configuration.exists():
        shutil.copyfile(expected, configuration)
        configuration.chmod(0o600)
    archive = directory / "archives"
    archive.mkdir(exist_ok=True, mode=0o700)
    temporary = directory / "tmp"
    temporary.mkdir(exist_ok=True, mode=0o700)
    return {
        "DAGSTER_HOME": str(home),
        "COUNTYIQ_ARCHIVE_DIR": str(archive),
        "COUNTYIQ_BACKFILL_STATE_DIR": str(directory / "intelligence"),
        "COUNTYIQ_SUBSCRIPTION_STATE_DIR": str(directory / "subscription"),
        "TMPDIR": str(temporary),
        "PYTHONPATH": str(ROOT / "pipelines"),
    }


def command_for(arguments) -> list[str]:
    if arguments.script:
        tail = arguments.arguments
        if tail[:1] == ["--"]:
            tail = tail[1:]
        return [
            sys.executable,
            str(ROOT / "pipelines/scripts" / SCRIPTS[arguments.script]),
            *tail,
        ]
    if arguments.arguments:
        raise ValueError("Trailing arguments apply only to a named script")
    command = [sys.executable, "-m", "countyiq.run_job"]
    if arguments.report_run:
        return [*command, "--report-run", arguments.report_run]
    command.extend(["--job", arguments.job])
    if arguments.assets:
        command.extend(["--assets", *arguments.assets])
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--job")
    target.add_argument("--report-run")
    target.add_argument("--script", choices=SCRIPTS)
    parser.add_argument("--assets", nargs="+", default=[])
    connection = parser.add_mutually_exclusive_group(required=True)
    connection.add_argument("--ssh-target")
    connection.add_argument(
        "--local",
        action="store_true",
        help="Use explicit local development DATABASE_* settings",
    )
    parser.add_argument("--identity-file", type=Path)
    parser.add_argument(
        "--state-dir", type=Path, default=Path.home() / ".local/state/countyiq/pipeline"
    )
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    if arguments.ssh_target and arguments.identity_file is None:
        parser.error("A production connection requires --identity-file")
    if arguments.assets and not arguments.job:
        parser.error("--assets applies only to a job")
    try:
        arguments.state_dir = arguments.state_dir.expanduser().absolute()
        state = prepare_state(arguments.state_dir)
        with (arguments.state_dir / "run.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            command = command_for(arguments)
            if arguments.local:
                return run_command(command, {**os.environ, **state})
            with PipelineSession(
                root=ROOT,
                target=arguments.ssh_target,
                identity=arguments.identity_file.expanduser(),
            ) as session:
                # Production configuration comes only from the authenticated
                # session. Inherited development settings cannot redirect it.
                environment = {
                    key: value
                    for key, value in os.environ.items()
                    if not key.startswith(
                        (
                            "DATABASE_",
                            "COUNTYIQ_",
                            "R2_",
                            "S3_",
                            "DAGSTER_",
                            "OPENROUTER_",
                            "SLACK_",
                        )
                    )
                }
                environment.update(session.environment)
                environment.update(state)
                print(
                    f"Running locally against VPS release {session.reference}",
                    flush=True,
                )
                return run_command(command, environment, session)
    except BlockingIOError:
        print("Another pipeline uses this local state directory.", file=sys.stderr)
    except (ValueError, RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
