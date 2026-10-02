from __future__ import annotations

from pathlib import Path

from Extract import pdf_reader


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
            FakePage([[["Name", "Amount"], ["Alice", "10"], ["Bob", "20"]]], text="Name Amount\nAlice 10\nBob 20"),
            FakePage([[["Type", "Value"], ["Revenue", "100"]]], text="Type Value\nRevenue 100"),
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakePdfPlumber:
    def open(self, input_path: Path) -> FakePdf:
        return FakePdf()


def test_read_pdf_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf_reader, "pdfplumber", FakePdfPlumber())
    input_path = tmp_path / "sample.pdf"
    input_path.write_bytes(b"%PDF-1.4")

    result = pdf_reader.read_pdf_file(input_path)

    assert result["page_count"] == 2
    assert result["pages"][0]["text"] == "Name Amount\nAlice 10\nBob 20"
    assert result["pages"][0]["tables"][0]["rows"][0] == ["Name", "Amount"]
    assert result["pages"][1]["tables"][0]["rows"][1] == ["Revenue", "100"]


class EmptyPdf:
    def __init__(self) -> None:
        self.pages = [FakePage([], text="")]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class EmptyPdfPlumber:
    def open(self, input_path: Path) -> EmptyPdf:
        return EmptyPdf()


def test_read_pdf_file_handles_pdf_without_tables(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf_reader, "pdfplumber", EmptyPdfPlumber())
    input_path = tmp_path / "blank.pdf"
    input_path.write_bytes(b"%PDF-1.4")

    result = pdf_reader.read_pdf_file(input_path)

    assert result["page_count"] == 1
    assert result["pages"][0]["tables"] == []
    assert result["pages"][0]["text"] == ""
