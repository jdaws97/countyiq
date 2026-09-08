**CountyIQ: WebAssembly and runtime optimization assessment — September 5, 2026**

Recommendation: keep Python for FastAPI and Dagster, prioritize database loading and map data representation, and consider a native Rust component only where profiling establishes a substantial CPU or memory cost. WebAssembly has credible future uses for browser computation and isolated plugins. The current evidence does not justify moving the backend to Wasm.

This is a research assessment of the current working tree, existing benchmark records, and primary documentation. No new runtime benchmark, load test, paid inference, deployment, or application change was performed. Historical measurements below are explicitly identified; proposed benefits remain hypotheses. Deployment status is separate from this assessment.

**What choosing Wasm actually changes**

WebAssembly is a compilation target and execution format. Rust or C++ can compile to native machine code for the VPS, or to Wasm for a browser or a runtime such as Wasmtime. Its design combines portable execution with sandboxed computation; it does not promise that a particular program will outperform its native equivalent. [WebAssembly goals](https://webassembly.org/docs/high-level-goals/)

Three different proposals should therefore be evaluated separately:

| Proposal | Potential benefit | Assessment for CountyIQ |
| --- | --- | --- |
| Run existing Python through Wasm/Pyodide | Execute Python in browser environments | Poor backend optimization candidate; this preserves a Python runtime and changes its environment |
| Rewrite a hot operation in Rust, compile natively | Lower CPU cost or memory use in that operation | Plausible, supported by the existing fetch benchmark; benchmark the full integration |
| Compile a Rust operation to Wasm | Run the same computational core in a browser, or isolate a plugin | Useful if CountyIQ needs those capabilities; speed still requires measurement |

Pyodide is a port of CPython to WebAssembly, not automatic conversion of arbitrary Python logic into optimized Rust-like machine code. Its current compatibility documentation lists limitations around threading, multiprocessing, sockets, and browser networking. These are Pyodide-specific constraints, not a claim that every Wasm runtime has identical limitations. CountyIQ's threaded fetcher, PostgreSQL driver, subprocess/browser scraping, and Dagster integration would require compatibility work. [Pyodide overview](https://pyodide.org/en/stable/), [Python compatibility](https://pyodide.org/en/stable/usage/wasm-constraints.html)

Wasmtime documents compilation-versus-execution tradeoffs, bounds-check optimization, and target CPU configuration. These are reasons to measure a pinned runtime and workload, rather than assign Wasm a universal speed multiplier. For CountyIQ's trusted code on one VPS, my inference is that native compilation is the simpler first comparison when CPU performance is the goal. [Wasmtime execution tuning](https://docs.wasmtime.dev/examples-fast-execution.html)

**Evidence already present in CountyIQ**

The [ArcGIS benchmark record](/home/jdaws/countyiq/benchmarks/arcgis-ingestion/README.md:17) contains one complete live-source run per implementation on August 31, 2026. Each fetched 175,928 features with all fields and geometry, using 2,000-feature pages and four concurrent requests:

| Fetch implementation | Wall time | Peak RSS |
| --- | ---: | ---: |
| Python, buffer every page | 50.72 s | 1,329,892 KiB, approximately 1.27 GiB |
| Python, four-page window | 35.58 s | 164,020 KiB, approximately 160 MiB |
| Native Rust, four-page window, gzip enabled | 30.94 s | 49,712 KiB, approximately 49 MiB |

Bounded Python reduced peak RSS by 87.7%. Rust used another 69.7% less memory than bounded Python; its observed wall time was 13.0% shorter. These are implementation comparisons, not isolated language effects. Network conditions, runtime/library choices, and compression behavior must be controlled in a repeat. Matching PIDN fingerprints establish identity coverage, not complete field, geometry, or SCD2 equivalence.

The [production parcel asset](/home/jdaws/countyiq/pipelines/countyiq/assets/arcgis/parcels.py:135) already uses the bounded Python iterator. The 88% improvement is therefore already represented in current source. This benchmark excludes database writes, full parsing, archive persistence, and end-to-end Dagster execution. It contains no Wasm candidate. A smaller Rust worker would also leave Dagster's own memory footprint in place. Lower memory use creates capacity on the VPS; it does not by itself reduce a fixed hosting bill.

The [existing proximity benchmark](/home/jdaws/countyiq/output/nearby-geography-benchmark-20260904.json) measured indexed PostGIS queries on an isolated local temporary table containing 175,928 parcel geometries. Its nine cases took approximately 23–456 ms. These are database execution measurements, not API response times or production timings, and there is no comparable unindexed timing in that artifact. They show a relevant database component to profile. [Migration 062](/home/jdaws/countyiq/pipelines/alembic/versions/062_parcel_geography_index.py:10) adds the geography expression index; this assessment does not assert that it has been deployed.

**Optimization candidates, in recommended order**

1. **Measure and improve ingestion's database staging.** The parcel asset uses `execute_batch` for attribute inserts, then another batch of geometry updates. Compare this with bounded `COPY` into a temporary input table and a set-based geometry conversion. PostgreSQL documents lower bulk-loading overhead for `COPY`. Preserve the existing transaction, PIDN semantics, source archive, completeness guards, geometry behavior, and SCD2 comparison. The candidate is a database access change that Python can drive; no language rewrite is required. Actual end-to-end savings are unmeasured. [Current staging](/home/jdaws/countyiq/pipelines/countyiq/assets/arcgis/parcels.py:148), [geometry update](/home/jdaws/countyiq/pipelines/countyiq/assets/arcgis/parcels.py:321), [PostgreSQL bulk loading](https://www.postgresql.org/docs/16/populate.html#POPULATE-COPY)

2. **Measure map payloads and prototype vector tiles if they are substantial.** [MapView](/home/jdaws/countyiq/frontend/src/pages/MapView.tsx:324) fetches several viewport GeoJSON responses, merges features, and deduplicates PIDNs. [Static overlays](/home/jdaws/countyiq/api/routes/layers.py:46) return every current geometry in their layer. PostGIS can produce binary MVT tiles, and deck.gl's `MVTLayer` loads visible tiles with worker parsing and binary data support. This could reduce repeated transfer, object creation, and main-thread processing. The opportunity comes from data representation and work placement; custom Wasm is optional. Preserve PIDN as a string property across tiles and retrieve full geometry for exact property inspection. Tile precision, freshness, authenticated access, worker bundling, and existing content-security policy need integration review. [PostGIS ST_AsMVT](https://postgis.net/docs/ST_AsMVT.html), [deck.gl MVTLayer](https://deck.gl/docs/api-reference/geo-layers/mvt-layer)

3. **Profile Python parsing and JSON conversion before adding native code.** The parcel asset writes per-feature JSON archives and converts ArcGIS rings using a Python coordinate loop. API map routes decode PostGIS GeoJSON into Python objects and build response objects. Compare fewer intermediate representations and an established native JSON library before writing a custom worker. `orjson` is one benchmark candidate, with differences such as bytes output and serialization semantics to check against existing contracts. If a custom CPU kernel remains worthwhile, PyO3 supports native Rust extensions callable from Python. Keep calls batched so converting Python objects does not consume the saving. [Geometry helper](/home/jdaws/countyiq/pipelines/countyiq/lib/geometry.py:17), [API conversion](/home/jdaws/countyiq/api/routes/parcels.py:189), [orjson documentation](https://github.com/ijl/orjson), [PyO3 guide](https://pyo3.rs/main/)

4. **Tune API query work before replacing FastAPI.** The API already has a bounded connection pool, so adding pooling is not a new opportunity. Separate pool wait, query execution, row conversion, response serialization, and transfer time. Inspect representative spatial plans and repeated work within property requests. PostGIS `ST_DWithin` supports index-assisted candidate filtering. Moving the HTTP layer to Rust, Go, TypeScript, or Wasm would leave those database operations to perform. There is no measured basis here for a whole-API rewrite. [Connection pool](/home/jdaws/countyiq/api/lib/database.py:1), [PostGIS ST_DWithin](https://postgis.net/docs/ST_DWithin.html)

5. **Use existing LLM timing and token evidence.** The [harness](/home/jdaws/countyiq/pipelines/countyiq/lib/llm_harness.py:739) records elapsed time and cached-token information around external provider calls. Changing its host language does not change the provider's token pricing or generation work. Investigate unnecessary calls, repeated context, caching effectiveness, and configured concurrency from those records. These require quality and cost evaluation; no prompt or concurrency change is proposed as an automatic optimization. CPU preprocessing could still be a separate hotspot, but its share has not been established.

**Where Wasm could provide a real additional capability**

A future interactive parcel-analysis tool could perform repeated polygon operations in a browser worker using a Rust core compiled to Wasm. That could improve responsiveness or avoid server round trips for calculations over data already loaded. Current `geometryBounds` performs allocations while walking coordinates, but it runs during parcel fitting; there is no evidence it is a meaningful hotspot. Start with a single-pass TypeScript implementation if profiling points there. For larger operations, compare optimized TypeScript and native library options against Wasm, including download, startup, memory conversion, and computation. Batch typed buffers across the boundary. The Rust/Wasm project documents the separation between JavaScript objects and Wasm linear memory; deck.gl documents binary buffers and workers as alternatives to expensive object processing. [Current bounds helper](/home/jdaws/countyiq/frontend/src/lib/mapViewport.ts:51), [Rust/JavaScript interoperation](https://rustwasm.github.io/book/reference/js-ffi.html), [deck.gl performance](https://deck.gl/docs/developer-guide/performance)

Wasm could also isolate future third-party parsers or customer-supplied calculations. Wasmtime exposes host functionality through explicit interfaces and provides capability-based filesystem access. That is a substantive isolation benefit. It would need a narrow plugin interface, bounded resources, and output validation; sandboxing cannot establish the correctness of a parcel association or source claim. No such plugin requirement was identified in the reviewed code. [Wasmtime security model](https://docs.wasmtime.dev/security.html)

**A bounded way to decide**

Record CPU time, elapsed time, peak RSS, database time, and transferred bytes for one representative ingestion and several map/property requests. For example, if only 20 ms of a 100 ms request is replaceable Python CPU work, making that part five times faster yields 84 ms overall. This is illustrative arithmetic, not a CountyIQ measurement.

Replay the same frozen source pages through current Python, optimized Python, and the native Rust candidate. Add a Wasm build only for an explicit browser or isolation hypothesis, using the same computational core as native Rust where possible. Separate replay measurements from remote-fetch measurements, hold compression and concurrency constant, alternate execution order, and report repeated-run distributions. Measure the full worker/orchestrator combination, not just a small subprocess.

For ingestion acceptance, reconcile fields, geometry, missing/null behavior, PIDNs, archive receipts, and SCD2 outcomes in an isolated test database. For map acceptance, compare payload bytes, interaction latency, browser memory, tile-boundary selection, full-geometry inspection, and mobile behavior. Proposed decision thresholds are a clear user-visible improvement or meaningful memory headroom at acceptable maintenance cost; no universal speedup percentage is established by this research.

The most useful next experiment is a measured comparison of current parcel staging against `COPY`, followed by map payload profiling. Native Rust remains a credible memory optimization for a narrow worker. Wasm should be selected when browser execution or plugin isolation is part of the requirement and the complete implementation wins the relevant benchmark.
