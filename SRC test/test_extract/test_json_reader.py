from __future__ import annotations

import json
from pathlib import Path

from Extract.json_reader import read_json_file


def test_read_json_file(tmp_path: Path) -> None:
    input_path = tmp_path / "sample.json"
    input_path.write_text(json.dumps({"name": "Ada", "skills": ["python", "csv"]}), encoding="utf-8")

    result = read_json_file(input_path)

    assert result["name"] == "Ada"
    assert result["skills"] == ["python", "csv"]
