"""Retire old CountyIQ images and bound disposable Docker build cache.

The default is a read-only plan. Apply requires valid current/previous release
receipts and holds the same lock as deployment throughout inspection and cleanup.
"""

from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

RELEASE_DIRECTORY = Path("/var/lib/countyiq/releases")
EXTRA_RELEASES = Path("/etc/countyiq/retained-releases.txt")
DEPLOY_LOCK = Path("/var/lock/countyiq-deploy.lock")
REPOSITORIES = {
    "countyiq-api": "api_image",
    "countyiq-migrate": "migrate_image",
    "countyiq-dagster": "dagster_image",  # Historical releases remain rollback points.
    "countyiq-web": "web_image",
}
COMMIT = re.compile(r"[0-9a-f]{40}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
BUILD_CACHE_KEEP = "4GB"
IMAGE_GRACE = datetime.timedelta(hours=1)


@dataclass(frozen=True)
class Image:
    identity: str
    created: datetime.datetime
    tags: tuple[str, ...]


def command(*arguments: str, timeout: int = 60) -> str:
    result = subprocess.run(
        list(arguments), capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode:
        # Docker inspection is deliberately limited to non-secret metadata.
        raise RuntimeError(f"{arguments[0]} {arguments[1]} failed")
    return result.stdout


def receipt_repositories(receipt: dict[str, str]) -> dict[str, str]:
    """Validate images recorded by either current or historical release receipts."""
    if not all(field in receipt for field in ("api_image", "web_image")):
        raise ValueError("Release receipt has no application image identities")
    if not any(field in receipt for field in ("migrate_image", "dagster_image")):
        raise ValueError("Release receipt has no migration image identity")
    repositories = {
        repository: field
        for repository, field in REPOSITORIES.items()
        if field in receipt
    }
    for field in repositories.values():
        if not IMAGE_ID.fullmatch(receipt[field]):
            raise ValueError("Release receipt has no valid image identity")
    return repositories


def read_receipt(path: Path) -> dict[str, str]:
    fields = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key in fields:
            raise ValueError("Invalid or duplicate field in release receipt")
        fields[key] = value
    if not COMMIT.fullmatch(fields.get("deploy_ref", "")):
        raise ValueError("Release receipt has no valid commit")
    receipt_repositories(fields)
    return fields


def protected_receipts(
    directory: Path = RELEASE_DIRECTORY, extra_releases: Path = EXTRA_RELEASES
) -> list[dict[str, str]]:
    current = read_receipt(directory / "current.env")
    previous = current.get("previous_ref", "")
    if previous != "none" and not COMMIT.fullmatch(previous):
        raise ValueError("Current receipt has no valid previous release")
    references = {current["deploy_ref"]}
    if previous != "none":
        references.add(previous)
    if extra_releases.exists():
        for line in extra_releases.read_text().splitlines():
            reference = line.partition("#")[0].strip()
            if not reference:
                continue
            if not COMMIT.fullmatch(reference):
                raise ValueError("Additional retained releases must be full commits")
            references.add(reference)
    receipts = [current]
    for reference in sorted(references - {current["deploy_ref"]}):
        matches = list(directory.glob(f"*-{reference}.env"))
        if len(matches) != 1:
            raise ValueError("A retained release needs exactly one saved receipt")
        receipt = read_receipt(matches[0])
        if receipt["deploy_ref"] != reference:
            raise ValueError("Saved release receipt does not match its filename")
        receipts.append(receipt)
    return receipts


def image_inventory() -> list[Image]:
    identities = sorted(
        set(command("docker", "image", "ls", "-q", "--no-trunc").split())
    )
    if not identities or any(not IMAGE_ID.fullmatch(item) for item in identities):
        raise ValueError("Docker did not return a valid image inventory")
    template = (
        '{"id":{{json .Id}},"created":{{json .Created}},"tags":{{json .RepoTags}}}'
    )
    output = command("docker", "image", "inspect", "--format", template, *identities)
    images = []
    for line in output.splitlines():
        item = json.loads(line)
        created = datetime.datetime.fromisoformat(item["created"])
        if created.tzinfo is None or not IMAGE_ID.fullmatch(item["id"]):
            raise ValueError("Docker image metadata is incomplete")
        images.append(Image(item["id"], created, tuple(item["tags"] or [])))
    if len(images) != len(identities):
        raise ValueError("Docker image inventory changed during inspection")
    return images


def container_images() -> set[str]:
    containers = command("docker", "container", "ls", "--all", "--quiet").split()
    if not containers:
        raise ValueError("No containers found; refusing an unexpected empty host")
    images = set(
        command(
            "docker", "container", "inspect", "--format", "{{.Image}}", *containers
        ).split()
    )
    if any(not IMAGE_ID.fullmatch(item) for item in images):
        raise ValueError("Container image metadata is incomplete")
    return images


def removal_plan(
    images: list[Image],
    receipts: list[dict[str, str]],
    used_images: set[str],
    now: datetime.datetime,
) -> list[str]:
    by_tag = {tag: image for image in images for tag in image.tags}
    protected = set(used_images)
    for receipt in receipts:
        for repository, field in receipt_repositories(receipt).items():
            tag = f"{repository}:{receipt['deploy_ref']}"
            image = by_tag.get(tag)
            if image is None or image.identity != receipt[field]:
                raise ValueError(
                    f"Retained release image is missing or mismatched: {tag}"
                )
            protected.add(image.identity)
    candidates = []
    for image in images:
        if image.identity in protected or now - image.created < IMAGE_GRACE:
            continue
        for tag in image.tags:
            repository, separator, reference = tag.partition(":")
            if separator and repository in REPOSITORIES and COMMIT.fullmatch(reference):
                candidates.append(tag)
    return sorted(candidates)


def run(*, apply: bool) -> None:
    if apply and os.geteuid() != 0:
        raise PermissionError("Retention apply must run as root")
    with DEPLOY_LOCK.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Retention skipped: a deployment or another cleanup holds the lock.")
            return
        receipts = protected_receipts()
        images = image_inventory()
        used_images = container_images()
        candidates = removal_plan(
            images, receipts, used_images, datetime.datetime.now(datetime.UTC)
        )
        print(
            "Retained releases: " + ", ".join(item["deploy_ref"] for item in receipts)
        )
        print(f"Old CountyIQ image tags eligible for removal: {len(candidates)}")
        for tag in candidates:
            print(f"  {tag}")
        print(f"Unused build-cache retention target: {BUILD_CACHE_KEEP}")
        if not apply:
            print("Read-only plan; use --apply to perform this cleanup.")
            return
        free_before = os.statvfs("/")
        for tag in candidates:
            # Never force removal or prune parents; Docker also rejects images
            # referenced by a container created since the initial inspection.
            command("docker", "image", "rm", "--no-prune", tag, timeout=300)
        command(
            "docker",
            "builder",
            "prune",
            "--all",
            "--force",
            "--keep-storage",
            BUILD_CACHE_KEEP,
            timeout=1800,
        )
        # Verify the rollback contract again after Docker has reclaimed layers.
        removal_plan(
            image_inventory(),
            receipts,
            container_images(),
            datetime.datetime.now(datetime.UTC),
        )
        free_after = os.statvfs("/")
        reclaimed = (
            free_after.f_bavail * free_after.f_frsize
            - free_before.f_bavail * free_before.f_frsize
        )
        print(f"Cleanup completed; filesystem available bytes changed by {reclaimed}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    try:
        run(apply=arguments.apply)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Docker retention stopped: {error}")
        raise SystemExit(1)
