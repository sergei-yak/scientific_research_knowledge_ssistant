"""Isolated, timed PDF inspection using the shared parser; never OCR or execute PDF content."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pymupdf

from research_assistant.collections.contracts import LIMITS
from research_assistant.contracts import PaperManifestEntry
from research_assistant.ingestion.pdf import normalize_block, parse_pages

PARSER_TIMEOUT_SECONDS = 60
MAX_PAGE_CHARACTERS = 100_000
MAX_PDF_CHARACTERS = 2_000_000
IMPORT_POLICY = {'format': 'user-import-policy-v1', 'parser_timeout_seconds': PARSER_TIMEOUT_SECONDS,
                 'max_page_characters': MAX_PAGE_CHARACTERS, 'max_pdf_characters': MAX_PDF_CHARACTERS,
                 'limits': LIMITS.model_dump()}


def inspect_pdf(path: Path) -> dict:
    """Validate actual bytes/pages, report omitted blank pages, and keep source coordinates unchanged."""
    size = path.stat().st_size
    if not 0 < size <= LIMITS.max_pdf_bytes:
        raise ValueError('PDF byte count is empty or exceeds 25 MiB')
    with path.open('rb') as handle:
        if handle.read(5) != b'%PDF-':
            raise ValueError('Input has no PDF signature')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pymupdf.open(path) as pdf:
        if not pdf.is_pdf or pdf.needs_pass:
            raise ValueError('Encrypted or non-PDF input is unsupported')
        if not 0 < len(pdf) <= LIMITS.max_pdf_pages:
            raise ValueError('PDF page count is empty or exceeds 100 pages')
        page_count = len(pdf)
        title = normalize_block((pdf.metadata or {}).get('title') or '')[:300]
    # Content-based metadata stays identical when the same PDF is supplied through another input/collection.
    uri = 'userpdf://' + digest
    manifest = PaperManifestEntry(paper_id='pdf-' + digest,
        title=title or 'Research PDF ' + digest[:12], source_url=uri, source_sha256=digest,
        local_path=str(path.resolve()), rights='Provided by user; redistribution rights not independently verified',
        rights_url=uri, selected_pages=list(range(1, page_count + 1)),
        selection_reason='All readable text pages; blank/image-only pages explicitly listed as omitted')
    pages = parse_pages(manifest, skip_empty=True, max_page_characters=MAX_PAGE_CHARACTERS,
                        max_total_characters=MAX_PDF_CHARACTERS)
    if not pages:
        raise ValueError('PDF has no readable text; scanned PDFs require unsupported OCR')
    selected = [p['page'] for p in pages]
    manifest = PaperManifestEntry.model_validate({**manifest.model_dump(), 'selected_pages': selected})
    return {'manifest': manifest.model_dump(mode='json'), 'pages': pages,
            'pdf_pages': page_count, 'indexed_pages': selected,
            'omitted_pages': [p for p in range(1, page_count + 1) if p not in selected],
            'source_sha256': digest, 'byte_count': size,
            'figures_tables_equations_verified': False, 'ocr_performed': False}


def main() -> None:
    """Write exactly one inspection result; parent enforces a 60-second subprocess deadline."""
    try:
        result = {'status': 'passed', **inspect_pdf(Path(sys.argv[1]))}
    except Exception as exc:
        result = {'status': 'failed', 'message': str(exc)[:500]}
    with Path(sys.argv[2]).open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + '\n')
    raise SystemExit(0 if result['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
