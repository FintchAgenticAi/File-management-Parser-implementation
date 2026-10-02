from __future__ import annotations

import csv
import json
from hashlib import sha256
from pathlib import Path

from fastapi import HTTPException

from app.config import EXTRACT_DIR
from app.schemas import CSVFileDetails, CSVIncludedDetails, DataCategory, FileProcessingContext, FileType


_SUPPORTED_FILE_TYPES = {item.value for item in FileType}


def _metadata_path_for(csv_path: Path) -> Path:
    return csv_path.parent / f"{csv_path.stem}.meta.json"


def compute_file_hash(file_bytes: bytes) -> str:
    return sha256(file_bytes).hexdigest()


def find_existing_csv_details_by_hash(file_hash: str, base_dir: Path = EXTRACT_DIR) -> CSVFileDetails | None:
    for metadata_path in base_dir.glob("*.meta.json"):
        try:
            details = CSVFileDetails.model_validate_json(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if details.file_hash == file_hash:
            return details
    return None


def store_csv_metadata(
    csv_path: Path,
    original_filename: str,
    context: FileProcessingContext,
    processor: str,
    file_hash: str,
) -> CSVFileDetails:
    details = CSVFileDetails(
        filename=csv_path.name,
        original_filename=original_filename,
        processor=processor,
        file_hash=file_hash,
        file_type=context.file_type,
        data_category=context.data_category,
        country=context.country,
        year=context.year,
        batch_name=context.batch_name,
        csv_path=str(csv_path),
    )
    metadata_path = _metadata_path_for(csv_path)
    metadata_path.write_text(details.model_dump_json(indent=2), encoding="utf-8")
    return details


def load_csv_metadata(filename: str, base_dir: Path = EXTRACT_DIR) -> CSVFileDetails:
    csv_path = base_dir / filename
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="CSV file not found.")

    metadata_path = _metadata_path_for(csv_path)
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="CSV metadata not found.")

    return CSVFileDetails.model_validate_json(metadata_path.read_text(encoding="utf-8"))


def load_csv_included_details(filename: str, base_dir: Path = EXTRACT_DIR) -> CSVIncludedDetails:
    details = load_csv_metadata(filename, base_dir=base_dir)
    csv_path = base_dir / details.filename

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = reader.fieldnames
            if columns is None:
                raise HTTPException(status_code=422, detail="CSV file is missing a header row.")

            rows = [
                {column: value or "" for column, value in row.items() if column is not None}
                for row in reader
            ]
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV file must be UTF-8 encoded.") from exc
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail=f"Invalid CSV file: {exc}") from exc

    return CSVIncludedDetails(columns=columns, row_count=len(rows), rows=rows)


def resolve_processing_plan(filename: str, context: FileProcessingContext) -> dict[str, str]:
    suffix = Path(filename).suffix.lower().lstrip(".")
    input_type = context.file_type.value

    if input_type not in _SUPPORTED_FILE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported input file type: {input_type}",
        )

    if suffix != input_type:
        raise HTTPException(
            status_code=422,
            detail=f"File type {input_type} does not match uploaded file extension {suffix}.",
        )

    return {
        "file_type": context.file_type.value,
        "data_category": context.data_category.value,
        "year": str(context.year),
        "batch_name": context.batch_name,
        "processor": "file_manager",
    }
