from __future__ import annotations

import csv
from pathlib import Path

from convert.xml_converter import convert_xml_to_csv


def test_convert_xml_to_csv(tmp_path: Path) -> None:
    input_path = tmp_path / "sample.xml"
    input_path.write_text(
        "<rows>"
        "<row><id>1</id><name>Alice</name><amount>100</amount></row>"
        "<row><id>2</id><name>Bob</name><amount>200</amount></row>"
        "<row><id>3</id><name>Charlie</name><amount>300</amount></row>"
        "</rows>",
        encoding="utf-8",
    )

    output_path = convert_xml_to_csv(input_path, output_dir=tmp_path / "Extract")

    assert output_path.exists()
    with output_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert rows[0]["id"] == "1"
    assert rows[0]["name"] == "Alice"
    assert rows[0]["amount"] == "100"
    assert rows[1]["id"] == "2"
    assert rows[2]["name"] == "Charlie"
