from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


class ConversionError(Exception):
    pass


def ensure_output_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def build_output_path(input_path: Path, output_dir: Path | None = None) -> Path:
    target_dir = ensure_output_dir(output_dir or input_path.parent / "Extract")
    return target_dir / f"{input_path.stem}.csv"


def scalar_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def flatten_mapping(prefix: str, value: Any, row: dict[str, str]) -> None:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            nested_prefix = f"{prefix}_{key}" if prefix else str(key)
            flatten_mapping(nested_prefix, nested_value, row)
        return
    if isinstance(value, list):
        row[prefix] = json.dumps(value, ensure_ascii=False)
        return
    row[prefix] = scalar_to_text(value)


def rows_from_json(data: Any) -> list[dict[str, str]]:
    if isinstance(data, list):
        rows: list[dict[str, str]] = []
        for item in data:
            if isinstance(item, Mapping):
                row: dict[str, str] = {}
                for key, value in item.items():
                    flatten_mapping(str(key), value, row)
                rows.append(row)
            else:
                rows.append({"value": scalar_to_text(item)})
        return rows
    if isinstance(data, Mapping):
        row: dict[str, str] = {}
        for key, value in data.items():
            flatten_mapping(str(key), value, row)
        return [row]
    return [{"value": scalar_to_text(data)}]


def write_csv(rows: Iterable[dict[str, str]], output_path: Path) -> Path:
    materialized_rows = list(rows)
    if not materialized_rows:
        raise ConversionError("No tabular data was found to write to CSV.")

    headers: list[str] = []
    seen: set[str] = set()
    for row in materialized_rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                headers.append(key)

    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in materialized_rows:
            writer.writerow({header: row.get(header, "") for header in headers})

    return output_path
