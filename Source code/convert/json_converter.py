from __future__ import annotations

from pathlib import Path

from Extract.json_reader import read_json_file

from convert.base_converter import build_output_path, rows_from_json, write_csv


def convert_json_to_csv(input_path: Path, output_dir: Path | None = None) -> Path:
    data = read_json_file(input_path)
    output_path = build_output_path(input_path, output_dir)
    return write_csv(rows_from_json(data), output_path)
