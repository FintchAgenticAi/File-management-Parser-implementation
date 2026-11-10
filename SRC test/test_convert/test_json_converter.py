from __future__ import annotations

import csv
import json
from pathlib import Path

from convert.json_converter import convert_json_to_csv


def test_convert_json_to_csv(tmp_path: Path) -> None:
    input_path = tmp_path / "sample.json"
    input_path.write_text(json.dumps([{"name": "Ada"}, {"name": "Grace"}]), encoding="utf-8")

    output_path = convert_json_to_csv(input_path, output_dir=tmp_path / "Extract")

    assert output_path.exists()
    with output_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert rows[0]["name"] == "Ada"
    assert rows[1]["name"] == "Grace"
