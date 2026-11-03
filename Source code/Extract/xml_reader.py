from __future__ import annotations

from pathlib import Path
from typing import Any

from Extract.base_reader import read_xml_file as _read_xml_file


def read_xml_file(input_path: Path) -> dict[str, Any]:
    return _read_xml_file(input_path)
