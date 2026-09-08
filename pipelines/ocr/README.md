# Pass 0 PDF preparation runtime

This project isolates Docling, RapidOCR and CPU Torch from the Dagster pipeline
environment. Install its locked dependencies from the repository root:

```sh
uv sync --project pipelines/ocr --locked
```

The pipeline helper `countyiq.lib.pass0_documents.read_pdf_source` reads native
PDF text first. It starts this project's interpreter when an image page has
insufficient text, or when the caller explicitly requests layout conversion.
The helper accepts PDF bytes and returns prepared text with page offsets and
PDF/text fingerprints. Evidence-mode extraction calls this helper when retained
text is insufficient. The standard Dagster image does not bundle the separate
OCR environment: scan preparation runs on an operator machine with this locked
runtime installed, and unavailable preparation remains pending.

`convert_pdf.py` is the worker entry point. It reads PDF bytes from standard
input, takes `--expected-pages`, and writes one JSON object containing the PDF
hash and every page's Markdown. The parent checks that hash and page count and
imposes a 210-second process deadline. The worker limits input to 8 MiB and 500
pages, uses four CPU threads and a 180-second conversion deadline, and rejects
partial conversion. Model weights may be downloaded on the first conversion;
deployment must prepare those assets before processing a backfill.

The archived research fixture
`output/pass0-redesign-2026-09-06/reusable-libraries/dillsburg-isolated-runtime.json`
records a successful four-page conversion through the parent process. It is a
member of `output/pass0-archive-2026-09-06-v99/evidence-and-code.tar.gz`. This checks
the runtime boundary and source provenance; it does not qualify Pass 0 fact
interpretation. See `docs/research/pass0-discovery.md` for the current design.
