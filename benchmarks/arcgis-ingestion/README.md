# ArcGIS ingestion runtime benchmark

This is an isolated, read-only benchmark. It does not write to PostgreSQL or
replace a production Dagster asset. It answers two different questions:

1. How expensive is CountyIQ's current Python/Dagster-shaped buffered fetch?
2. How much do bounded page processing and a small Rust runtime reduce peak RAM?

Both workers compute an order-independent identity fingerprint from every PIDN:
feature count, missing PIDN count, XOR of SHA-256 prefixes, and wrapping sum of
the same prefixes. A candidate only passes when the complete-run fingerprints
match. This is stronger than comparing row counts, but it is not a substitute
for CountyIQ's database constraints, SCD2 checks, source receipts, and sampled
field-level reconciliation.

## York County result (2026-08-31)

One complete live-source run per candidate used 2,000-feature pages, four
concurrent requests, geometry, and all source fields. `/usr/bin/time -v`
reported:

| Fetch implementation | Features | Wall time | Peak RSS |
|---|---:|---:|---:|
| Existing Python all-pages buffer | 175,928 | 50.72 s | 1,329,892 KiB (1.27 GiB) |
| Python four-page window | 175,928 | 35.58 s | 164,020 KiB (160 MiB) |
| Rust four-page window + gzip | 175,928 | 30.94 s | 49,712 KiB (49 MiB) |

Every run had zero missing PIDNs and the same fingerprints:
`xor=91e9294d5ffeeb54a13bd13d2b0dae3d` and
`sum=9a4c53bbb4944d4aee6313d2178663a5`. The source returned about 300 MB of
uncompressed JSON. The Python window removed about 88% of the current fetch
peak; Rust removed another 70% from the bounded Python worker.

These are fetch-only, single-run observations against a live remote endpoint,
not an end-to-end Dagster/PostgreSQL benchmark or a latency guarantee. Network
conditions varied materially during development. The result supports adopting
bounded Python page lifetime immediately; it does not by itself justify
rewriting CountyIQ's parsing, SCD2, evidence, or orchestration layers in Rust.
The production parcel asset now uses the bounded Python iterator.

## Build the Rust worker

From WSL at the repository root:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e CARGO_HOME=/tmp/cargo \
  -v "$PWD/benchmarks/arcgis-ingestion/rust-worker:/work" \
  -w /work \
  rust:1.89-slim-bookworm \
  cargo build --release
```

## Run comparable tests

Use the URL in `pipelines/config/counties/york.yaml`:

```bash
PARCELS_URL='https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0'

/usr/bin/time -v pipelines/.venv/bin/python \
  benchmarks/arcgis-ingestion/python_worker.py \
  --url "$PARCELS_URL" --mode parallel-buffered

/usr/bin/time -v pipelines/.venv/bin/python \
  benchmarks/arcgis-ingestion/python_worker.py \
  --url "$PARCELS_URL" --mode parallel-bounded

/usr/bin/time -v \
  benchmarks/arcgis-ingestion/rust-worker/target/release/countyiq-arcgis-bench \
  --url "$PARCELS_URL"
```

Run `--max-pages 5` first with `parallel-bounded` and Rust when testing a new
endpoint. The current `parallel-buffered` mode deliberately exercises the
existing all-pages-in-memory helper, so it only supports complete runs.

Keep batch size, concurrency, geometry, fields, and source constant. Alternate
the order of runs when collecting several samples because source and network
latency can dominate elapsed time. The primary comparison is maximum resident
set size from `/usr/bin/time -v`; compare elapsed time only across repeated
runs. Do not point this benchmark at a database.
