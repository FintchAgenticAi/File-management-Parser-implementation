from __future__ import annotations

from pathlib import Path
from typing import Any

from Extract.base_reader import read_json_file as _read_json_file


def read_json_file(input_path: Path) -> Any:
    return _read_json_file(input_path)
