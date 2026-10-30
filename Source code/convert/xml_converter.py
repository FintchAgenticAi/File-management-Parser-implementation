from __future__ import annotations

from pathlib import Path
from typing import Any

from Extract.xml_reader import read_xml_file

from convert.base_converter import build_output_path, write_csv


def _has_repeated_child_tags(node: dict[str, Any]) -> bool:
    children = node.get("children", []) or []
    tags = [child.get("tag") for child in children]
    return len(tags) != len(set(tags))


def _set_row_value(row: dict[str, str], key: str, value: str) -> None:
    if not key:
        return
    if key not in row or row[key] == "":
        row[key] = value
        return
    if row[key] == value:
        return

    suffix = 2
    candidate = f"{key}_{suffix}"
    while candidate in row:
        suffix += 1
        candidate = f"{key}_{suffix}"
    row[candidate] = value


def _flatten_record(node: dict[str, Any], row: dict[str, str], path: tuple[str, ...] = ()) -> None:
    current_path = path + (str(node["tag"]),)
    visible_path = current_path[1:] if len(current_path) > 1 else current_path

    for attr_name, attr_value in (node.get("attributes", {}) or {}).items():
        attr_key_path = visible_path + (f"attr_{attr_name}",)
        _set_row_value(row, "_".join(attr_key_path), str(attr_value))

    children = node.get("children", []) or []
    text = (node.get("text") or "").strip()

    if not children:
        key = "_".join(visible_path)
        _set_row_value(row, key, text)
        return

    for child in children:
        _flatten_record(child, row, current_path)


def _rows_from_xml(xml_tree: dict[str, Any]) -> list[dict[str, str]]:
    children = xml_tree.get("children", []) or []
    records: list[dict[str, Any]]

    if children and _has_repeated_child_tags(xml_tree):
        records = children
    else:
        records = [xml_tree]

    rows: list[dict[str, str]] = []
    for record in records:
        row: dict[str, str] = {}
        _flatten_record(record, row)
        rows.append(row)
    return rows


def convert_xml_to_csv(input_path: Path, output_dir: Path | None = None) -> Path:
    xml_tree = read_xml_file(input_path)
    output_path = build_output_path(input_path, output_dir)
    rows = _rows_from_xml(xml_tree)
    return write_csv(rows, output_path)
