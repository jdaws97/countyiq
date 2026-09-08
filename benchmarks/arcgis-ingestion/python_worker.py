#!/usr/bin/env python3
"""Read-only ArcGIS benchmark using CountyIQ's current Python client."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, TextIO

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "pipelines"))

from countyiq.lib.arcgis_client import (  # noqa: E402
    _fetch_page,
    fetch_all_features_parallel,
    iterate_feature_pages,
)

MASK_128 = (1 << 128) - 1


class Fingerprint:
    def __init__(self) -> None:
        self.count = 0
        self.missing = 0
        self.xor = 0
        self.sum = 0

    def add(self, value: Any) -> None:
        if value is None:
            self.missing += 1
            return
        digest = hashlib.sha256(str(value).encode("utf-8")).digest()
        number = int.from_bytes(digest[:16], "big")
        self.count += 1
        self.xor ^= number
        self.sum = (self.sum + number) & MASK_128


def get_count(url: str, where: str, timeout: int) -> int:
    response = requests.get(
        f"{url.rstrip('/')}/query",
        params={"where": where, "returnCountOnly": "true", "f": "json"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"ArcGIS count error: {payload['error']}")
    return int(payload["count"])


def bounded_parallel_pages(
    args: argparse.Namespace, expected_total: int
) -> Iterable[list[dict]]:
    total_pages = (expected_total + args.batch_size - 1) // args.batch_size
    selected_pages = min(args.max_pages or total_pages, total_pages)
    offsets = iter(page * args.batch_size for page in range(selected_pages))

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:

        def submit(offset: int):
            return executor.submit(
                _fetch_page,
                args.url,
                args.where,
                args.out_fields,
                4326,
                args.batch_size,
                offset,
                args.return_geometry,
            )

        pending = {}
        for offset in offsets:
            pending[submit(offset)] = offset
            if len(pending) == args.concurrency:
                break

        while pending:
            future = next(as_completed(pending))
            pending.pop(future)
            page = future.result()
            yield page
            del page, future

            try:
                offset = next(offsets)
            except StopIteration:
                continue
            pending[submit(offset)] = offset


def feature_pages(
    args: argparse.Namespace, expected_total: int
) -> Iterable[list[dict]]:
    if args.mode == "parallel-buffered":
        if args.max_pages is not None:
            raise ValueError("--max-pages is not supported by parallel-buffered mode")
        yield fetch_all_features_parallel(
            url=args.url,
            where=args.where,
            out_fields=args.out_fields,
            batch_size=args.batch_size,
            max_workers=args.concurrency,
            return_geometry=args.return_geometry,
            out_sr=4326,
        )
        return

    if args.mode == "parallel-bounded":
        yield from bounded_parallel_pages(args, expected_total)
        return

    pages = iterate_feature_pages(
        url=args.url,
        where=args.where,
        out_fields=args.out_fields,
        batch_size=args.batch_size,
        return_geometry=args.return_geometry,
        out_sr=4326,
        delay=0,
    )
    for page_number, page in enumerate(pages, start=1):
        if args.max_pages is not None and page_number > args.max_pages:
            break
        yield page


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--mode",
        choices=("parallel-buffered", "parallel-bounded", "streaming-sequential"),
        default="parallel-buffered",
    )
    parser.add_argument("--where", default="1=1")
    parser.add_argument("--out-fields", default="*")
    parser.add_argument("--pidn-field", default="PIDN")
    parser.add_argument("--batch-size", type=int, default=2_000)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--no-geometry", action="store_false", dest="return_geometry")
    parser.add_argument("--archive", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.batch_size <= 0 or args.concurrency <= 0:
        raise ValueError("batch size and concurrency must be greater than zero")
    if args.max_pages is not None and args.max_pages <= 0:
        raise ValueError("max pages must be greater than zero")

    started = time.perf_counter()
    expected_total = get_count(args.url, args.where, args.timeout)
    fingerprint = Fingerprint()
    feature_count = 0
    page_count = 0
    archive: TextIO | None = (
        args.archive.open("w", encoding="utf-8") if args.archive else None
    )

    try:
        for page in feature_pages(args, expected_total):
            page_count += 1
            feature_count += len(page)
            for feature in page:
                fingerprint.add(feature.get("attributes", {}).get(args.pidn_field))
                if archive is not None:
                    archive.write(json.dumps(feature, separators=(",", ":")))
                    archive.write("\n")
    finally:
        if archive is not None:
            archive.close()

    complete = args.max_pages is None and feature_count == expected_total
    if args.max_pages is None and feature_count != expected_total:
        raise RuntimeError(
            f"full run returned {feature_count} features but ArcGIS reported {expected_total}"
        )

    print(
        json.dumps(
            {
                "worker": f"python-{args.mode}",
                "expected_total": expected_total,
                "feature_count": feature_count,
                "fingerprinted_count": fingerprint.count,
                "pidn_missing": fingerprint.missing,
                "pidn_xor": f"{fingerprint.xor:032x}",
                "pidn_sum": f"{fingerprint.sum:032x}",
                "pages": page_count,
                "response_bytes": None,
                "batch_size": args.batch_size,
                "concurrency": args.concurrency,
                "return_geometry": args.return_geometry,
                "complete": complete,
                "elapsed_seconds": time.perf_counter() - started,
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
