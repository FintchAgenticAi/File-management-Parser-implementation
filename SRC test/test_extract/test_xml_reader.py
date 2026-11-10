from __future__ import annotations

from pathlib import Path

from Extract.xml_reader import read_xml_file


def test_read_xml_file(tmp_path: Path) -> None:
    input_path = tmp_path / "sample.xml"
    input_path.write_text("<root id='1'><item>value</item></root>", encoding="utf-8")

    result = read_xml_file(input_path)

    assert result["tag"] == "root"
    assert result["attributes"] == {"id": "1"}
    assert result["children"][0]["tag"] == "item"
    assert result["children"][0]["text"] == "value"
