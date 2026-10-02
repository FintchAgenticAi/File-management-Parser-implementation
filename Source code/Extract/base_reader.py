from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


class ReaderError(Exception):
    pass


def read_text_file(input_path: Path) -> str:
    return input_path.read_text(encoding="utf-8-sig")


def read_json_file(input_path: Path) -> Any:
    with input_path.open("r", encoding="utf-8-sig") as source_file:
        return json.load(source_file)


def _xml_element_to_object(element: ET.Element) -> dict[str, Any]:
    return {
        "tag": element.tag,
        "attributes": dict(element.attrib),
        "text": (element.text or "").strip(),
        "children": [_xml_element_to_object(child) for child in list(element)],
    }


def read_xml_file(input_path: Path) -> dict[str, Any]:
    tree = ET.parse(input_path)
    return _xml_element_to_object(tree.getroot())
