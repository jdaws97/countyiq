"""Protect rollback and live images while removing only disposable artifacts."""

import contextlib
import datetime
import fcntl
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import retention

NOW = datetime.datetime(2026, 9, 8, 16, tzinfo=datetime.UTC)
OLD = NOW - datetime.timedelta(days=3)
CURRENT = "a" * 40
PREVIOUS = "b" * 40
RETIRED = "c" * 40


def receipt(reference, previous="none"):
    result = {"deploy_ref": reference, "previous_ref": previous}
    for index, field in enumerate(retention.REPOSITORIES.values()):
        result[field] = "sha256:" + reference[0] * 63 + str(index)
    return result


def release_images(record):
    return [
        retention.Image(record[field], OLD, (f"{repository}:{record['deploy_ref']}",))
        for repository, field in retention.REPOSITORIES.items()
    ]


def write_receipt(path, record):
    path.write_text("".join(f"{key}={value}\n" for key, value in record.items()))


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.current = receipt(CURRENT, PREVIOUS)
        self.previous = receipt(PREVIOUS)
        self.receipts = [self.current, self.previous]
        self.images = release_images(self.current) + release_images(self.previous)
        self.used = {self.current["api_image"]}

    def test_keeps_releases_containers_recent_images_and_unrelated_tags(self):
        retired = release_images(receipt(RETIRED))
        self.images.extend(retired)
        # A stopped container still needs its old image.
        self.used.add(retired[0].identity)
        self.images.extend(
            [
                retention.Image(
                    "sha256:" + "d" * 64,
                    NOW - datetime.timedelta(minutes=30),
                    (f"countyiq-api:{'d' * 40}",),
                ),
                retention.Image(
                    "sha256:" + "e" * 64,
                    OLD,
                    (f"unrelated:{'e' * 40}", "countyiq-api:manual-pin"),
                ),
                retention.Image("sha256:" + "f" * 64, OLD, ()),
            ]
        )
        planned = retention.removal_plan(self.images, self.receipts, self.used, NOW)
        self.assertEqual(
            planned, [f"countyiq-dagster:{RETIRED}", f"countyiq-web:{RETIRED}"]
        )

    def test_keeps_other_tags_pointing_to_a_protected_image_identity(self):
        current = self.images[0]
        self.images[0] = retention.Image(
            current.identity, OLD, (*current.tags, f"countyiq-api:{RETIRED}")
        )
        self.assertEqual(
            retention.removal_plan(self.images, self.receipts, self.used, NOW), []
        )

    def test_missing_or_retagged_rollback_image_stops_the_whole_plan(self):
        for images in (
            self.images[:-1],
            [
                *self.images[:-1],
                retention.Image("sha256:" + "f" * 64, OLD, self.images[-1].tags),
            ],
        ):
            with self.subTest(images=images), self.assertRaises(ValueError):
                retention.removal_plan(images, self.receipts, self.used, NOW)

    def test_receipts_include_previous_and_explicitly_retained_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_receipt(root / "current.env", self.current)
            write_receipt(root / f"20260907T120000Z-{PREVIOUS}.env", self.previous)
            write_receipt(root / f"20260906T120000Z-{RETIRED}.env", receipt(RETIRED))
            pinned = root / "retained.txt"
            pinned.write_text(f"# Additional rollback point\n{RETIRED}\n")
            records = retention.protected_receipts(root, pinned)
            self.assertEqual(
                {record["deploy_ref"] for record in records},
                {CURRENT, PREVIOUS, RETIRED},
            )
            pinned.write_text("invalid-reference\n")
            with self.assertRaises(ValueError):
                retention.protected_receipts(root, pinned)

    def test_missing_previous_receipt_and_duplicate_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "current.env"
            write_receipt(current, self.current)
            with self.assertRaises(ValueError):
                retention.protected_receipts(root, root / "missing.txt")
            with current.open("a") as output:
                output.write(f"deploy_ref={RETIRED}\n")
            with self.assertRaises(ValueError):
                retention.read_receipt(current)

    def test_dry_run_does_not_issue_any_docker_mutations(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(retention, "DEPLOY_LOCK", Path(directory) / "deploy.lock"),
            patch.object(retention, "protected_receipts", return_value=self.receipts),
            patch.object(retention, "image_inventory", return_value=self.images),
            patch.object(retention, "container_images", return_value=self.used),
            patch.object(retention, "command") as command,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            retention.run(apply=False)
        command.assert_not_called()

    def test_apply_only_removes_planned_tags_and_cache_without_force_image_delete(self):
        images = self.images + release_images(receipt(RETIRED))
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(retention, "DEPLOY_LOCK", Path(directory) / "deploy.lock"),
            patch.object(retention.os, "geteuid", return_value=0),
            patch.object(retention, "protected_receipts", return_value=self.receipts),
            patch.object(
                retention, "image_inventory", side_effect=[images, self.images]
            ),
            patch.object(retention, "container_images", return_value=self.used),
            patch.object(retention, "command") as command,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            retention.run(apply=True)
        commands = [call.args for call in command.call_args_list]
        self.assertEqual(
            commands,
            [
                ("docker", "image", "rm", "--no-prune", f"{repository}:{RETIRED}")
                for repository in sorted(retention.REPOSITORIES)
            ]
            + [
                (
                    "docker",
                    "builder",
                    "prune",
                    "--all",
                    "--force",
                    "--keep-storage",
                    "4GB",
                )
            ],
        )

    def test_active_deployment_skips_before_reading_or_deleting_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "deploy.lock"
            with (
                lock_path.open("a") as active_lock,
                patch.object(retention, "DEPLOY_LOCK", lock_path),
                patch.object(retention.os, "geteuid", return_value=0),
                patch.object(retention, "protected_receipts") as receipts,
                patch.object(retention, "command") as command,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                fcntl.flock(active_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                retention.run(apply=True)
            receipts.assert_not_called()
            command.assert_not_called()

    def test_invalid_rollback_stops_before_image_removal_or_cache_pruning(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(retention, "DEPLOY_LOCK", Path(directory) / "deploy.lock"),
            patch.object(retention.os, "geteuid", return_value=0),
            patch.object(retention, "protected_receipts", return_value=self.receipts),
            patch.object(retention, "image_inventory", return_value=self.images[:-1]),
            patch.object(retention, "container_images", return_value=self.used),
            patch.object(retention, "command") as command,
            self.assertRaises(ValueError),
        ):
            retention.run(apply=True)
        command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
