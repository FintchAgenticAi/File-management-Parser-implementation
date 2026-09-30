from __future__ import annotations

import hashlib
from pathlib import Path

from convert.base_converter import build_output_path, write_csv


def _mime_type_for_suffix(suffix: str) -> str:
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime_map.get(suffix.lower(), "application/octet-stream")


def convert_image_to_csv(
    input_path: Path,
    output_dir: Path | None = None,
    original_filename: str | None = None,
) -> Path:
    file_bytes = input_path.read_bytes()
    output_path = build_output_path(input_path, output_dir)
    rows = [
        {
            "filename": original_filename or input_path.name,
            "image_type": input_path.suffix.lower().lstrip("."),
            "mime_type": _mime_type_for_suffix(input_path.suffix),
            "byte_size": str(len(file_bytes)),
            "sha256": hashlib.sha256(file_bytes).hexdigest(),
        }
    ]
    return write_csv(rows, output_path)
