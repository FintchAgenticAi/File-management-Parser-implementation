from __future__ import annotations

import logging
from hashlib import sha256
from pathlib import Path

from fastapi import HTTPException

from app.config import EXTRACT_DIR
from app.database import DatabaseError, get_batch_for_file
from app.schemas import CSVFileDetails, DataCategory, FileProcessingContext, FileType


_SUPPORTED_FILE_TYPES = {item.value for item in FileType}
_logger = logging.getLogger(__name__)


def compute_file_hash(file_bytes: bytes) -> str:
    return sha256(file_bytes).hexdigest()


def find_existing_csv_details_by_hash(file_hash: str, base_dir: Path = EXTRACT_DIR) -> CSVFileDetails | None:
    return None


def load_csv_metadata(filename: str, base_dir: Path = EXTRACT_DIR) -> CSVFileDetails:
    base_path = base_dir.resolve()
    csv_path = (base_path / filename).resolve()
    if csv_path.parent != base_path:
        raise HTTPException(status_code=400, detail="Invalid CSV filename.")
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="CSV file not found.")

    stem = csv_path.stem
    parts = stem.split("_")
    if len(parts) < 2 or not parts[0].isdigit():
        raise HTTPException(status_code=422, detail="CSV filename does not contain a valid batch name.")
    batch_name = "_".join(parts[1:-1]) if parts[-1].lower().startswith("v") else "_".join(parts[1:])
    try:
        batch = get_batch_for_file(csv_path.name)
    except DatabaseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CSVFileDetails(
        filename=csv_path.name,
        original_filename=None,
        data_batch_id=batch.data_batch_id if batch else None,
        file_type=FileType.csv,
        data_category=None,
        country=batch.country if batch else None,
        year=int(parts[0]),
        batch_name=batch.batch_name if batch else batch_name,
        csv_path=str(csv_path),
    )


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
