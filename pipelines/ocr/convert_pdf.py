"""Convert one PDF using the separately locked Pass 0 OCR runtime."""

import argparse
import hashlib
import io
import json
import sys

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import ConversionStatus, DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 500


def convert(pdf_bytes: bytes, expected_pages: int) -> dict:
    if not pdf_bytes.startswith(b"%PDF-") or len(pdf_bytes) > MAX_BYTES:
        raise ValueError("Input is not a PDF within the supported byte limit")
    if not 1 <= expected_pages <= MAX_PAGES:
        raise ValueError("Unsupported expected page count")
    options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        ocr_options=RapidOcrOptions(),
        accelerator_options=AcceleratorOptions(device="cpu", num_threads=4),
        document_timeout=180,
    )
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )
    converted = converter.convert(
        DocumentStream(name="proceeding.pdf", stream=io.BytesIO(pdf_bytes)),
        raises_on_error=False,
        max_num_pages=MAX_PAGES,
        max_file_size=MAX_BYTES,
    )
    if converted.status != ConversionStatus.SUCCESS or converted.errors:
        raise ValueError(f"PDF conversion is incomplete: {converted.status}")
    if set(converted.document.pages) != set(range(1, expected_pages + 1)):
        raise ValueError("PDF conversion did not preserve every source page")
    return {
        "document_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "pages": [
            converted.document.export_to_markdown(page_no=page).strip()
            for page in range(1, expected_pages + 1)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-pages", type=int, required=True)
    arguments = parser.parse_args()
    result = convert(sys.stdin.buffer.read(MAX_BYTES + 1), arguments.expected_pages)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
