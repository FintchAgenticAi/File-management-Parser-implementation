from __future__ import annotations

import csv
from pathlib import Path

from Extract import pdf_reader
from convert.pdf_converter import convert_pdf_to_csv


class FakePage:
    def __init__(self, tables: list[list[list[str]]], text: str = "") -> None:
        self._tables = tables
        self._text = text

    def extract_tables(self) -> list[list[list[str]]]:
        return self._tables

    def extract_text(self) -> str:
        return self._text


class FakePdf:
    def __init__(self) -> None:
        self.pages = [
            FakePage([[["Item", "Amount"], ["Alpha", "10"], ["Beta", "20"]]], text="Item Amount\nAlpha 10\nBeta 20"),
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakePdfPlumber:
    def open(self, input_path: Path) -> FakePdf:
        return FakePdf()


def test_convert_pdf_to_csv(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf_reader, "pdfplumber", FakePdfPlumber())
    input_path = tmp_path / "sample.pdf"
    input_path.write_bytes(b"%PDF-1.4")

    output_path = convert_pdf_to_csv(input_path, output_dir=tmp_path / "Extract")

    assert output_path.exists()
    with output_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert rows[0]["page_number"] == "1"
    assert rows[0]["table_number"] == "1"
    assert rows[0]["Item"] == "Alpha"
    assert rows[1]["Item"] == "Beta"


def test_convert_pdf_to_csv_falls_back_to_text(monkeypatch, tmp_path: Path) -> None:
    class TextOnlyPage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_tables(self) -> list[list[list[str]]]:
            return []

        def extract_text(self) -> str:
            return self._text

    class TextOnlyPdf:
        def __init__(self) -> None:
            self.pages = [TextOnlyPage("Line one\nLine two")]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class TextOnlyPlumber:
        def open(self, input_path: Path) -> TextOnlyPdf:
            return TextOnlyPdf()

    monkeypatch.setattr(pdf_reader, "pdfplumber", TextOnlyPlumber())
    input_path = tmp_path / "textonly.pdf"
    input_path.write_bytes(b"%PDF-1.4")

    output_path = convert_pdf_to_csv(input_path, output_dir=tmp_path / "Extract")

    with output_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert rows[0]["page_number"] == "1"
    assert rows[0]["line_number"] == "1"
    assert rows[0]["text"] == "Line one"
    assert rows[1]["text"] == "Line two"
