from __future__ import annotations

from pathlib import Path
from typing import Any

from Extract.base_reader import ReaderError

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def read_pdf_file(input_path: Path) -> dict[str, Any]:
    if pdfplumber is None:
        raise ReaderError("Reading PDF files requires the optional 'pdfplumber' package.")

    pages: list[dict[str, Any]] = []

    with pdfplumber.open(input_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            page_tables: list[dict[str, Any]] = []
            for table_number, table in enumerate(page.extract_tables() or [], start=1):
                normalized_rows = [
                    ["" if cell is None else str(cell).strip() for cell in row]
                    for row in table
                    if any(cell not in (None, "") for cell in row)
                ]
                if normalized_rows:
                    page_tables.append({"table_number": table_number, "rows": normalized_rows})

            pages.append({"page_number": page_number, "text": text, "tables": page_tables})

    return {
        "page_count": len(pages),
        "pages": pages,
    }
