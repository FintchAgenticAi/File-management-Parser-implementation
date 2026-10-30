from __future__ import annotations

from pathlib import Path

import pandas as pd

from Extract.base_reader import ReaderError
from Extract.pdf_reader import read_pdf_file

from convert.base_converter import build_output_path, write_csv


def _deduplicate_headers(headers: list[str]) -> list[str]:
    deduplicated: list[str] = []
    seen: set[str] = set()
    for index, header in enumerate(headers, start=1):
        candidate = header.strip() or f"column_{index}"
        while candidate in seen:
            candidate = f"{candidate}_{index}"
        seen.add(candidate)
        deduplicated.append(candidate)
    return deduplicated


def convert_pdf_to_csv(input_path: Path, output_dir: Path | None = None) -> Path:
    document = read_pdf_file(input_path)
    table_frames: list[pd.DataFrame] = []
    text_rows: list[dict[str, str]] = []

    for page in document["pages"]:
        page_number = str(page["page_number"])
        page_tables = page.get("tables", [])
        for table in page_tables:
            rows = table["rows"]
            if len(rows) < 2:
                continue

            max_columns = max(len(row) for row in rows)
            normalized_rows = [row + [""] * (max_columns - len(row)) for row in rows]
            header_row = _deduplicate_headers(normalized_rows[0])
            table_rows = normalized_rows[1:]
            table_frame = pd.DataFrame(table_rows, columns=header_row)
            table_frame.insert(0, "table_number", str(table["table_number"]))
            table_frame.insert(0, "page_number", page_number)
            table_frames.append(table_frame)

        if not page_tables:
            text = (page.get("text") or "").strip()
            if text:
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                for line_number, line in enumerate(lines, start=1):
                    text_rows.append(
                        {
                            "page_number": page_number,
                            "line_number": str(line_number),
                            "text": line,
                        }
                    )

    output_path = build_output_path(input_path, output_dir)
    if table_frames:
        combined_frame = pd.concat(table_frames, ignore_index=True)
        combined_frame.to_csv(output_path, index=False, encoding="utf-8-sig")
        return output_path

    if text_rows:
        write_csv(text_rows, output_path)
        return output_path

    raise ReaderError("No extractable tables or text were found in the PDF.")
