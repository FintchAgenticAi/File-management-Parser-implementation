from __future__ import annotations

import json
import logging
from hashlib import sha256
from pathlib import Path

from fastapi import HTTPException

from app.config import EXTRACT_DIR
from app.schemas import CSVFileDetails, DataCategory, FileProcessingContext, FileType


_SUPPORTED_FILE_TYPES = {item.value for item in FileType}
_logger = logging.getLogger(__name__)


def data_batch_id_for(year: int, batch_name: str, base_dir: Path = EXTRACT_DIR) -> int:
    """Return a stable sequential ID, starting at 1, for an uploaded batch."""
    metadata_entries: list[tuple[Path, dict[str, object]]] = []
    for metadata_path in sorted(base_dir.glob("*.meta.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(metadata, dict):
            metadata_entries.append((metadata_path, metadata))

    batch_ids: list[int] = []
    for _, metadata in metadata_entries:
        existing_id = metadata.get("data_batch_id")
        if isinstance(existing_id, int) and existing_id >= 1:
            batch_ids.append(existing_id)

    next_id = max(batch_ids, default=0) + 1
    assigned_batches: dict[tuple[object, object], int] = {}
    for metadata_path, metadata in metadata_entries:
        batch_key = (metadata.get("year"), metadata.get("batch_name"))
        existing_id = metadata.get("data_batch_id")
        if not isinstance(existing_id, int) or existing_id < 1:
            existing_id = assigned_batches.get(batch_key)
            if existing_id is None:
                existing_id = next_id
                next_id += 1
            metadata["data_batch_id"] = existing_id
            try:
                metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            except OSError:
                _logger.warning("Could not persist batch ID in metadata file: %s", metadata_path, exc_info=True)
        assigned_batches[batch_key] = existing_id
        if metadata.get("year") == year and metadata.get("batch_name") == batch_name:
            return existing_id

    return next_id


def _metadata_path_for(csv_path: Path) -> Path:
    return csv_path.parent / f"{csv_path.stem}.meta.json"


def compute_file_hash(file_bytes: bytes) -> str:
    return sha256(file_bytes).hexdigest()


def find_existing_csv_details_by_hash(file_hash: str, base_dir: Path = EXTRACT_DIR) -> CSVFileDetails | None:
    for metadata_path in base_dir.glob("*.meta.json"):
        try:
            details = CSVFileDetails.model_validate_json(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _logger.warning("Ignoring invalid CSV metadata file: %s", metadata_path, exc_info=True)
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
        data_batch_id=None,
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
    base_path = base_dir.resolve()
    csv_path = (base_path / filename).resolve()
    if csv_path.parent != base_path:
        raise HTTPException(status_code=400, detail="Invalid CSV filename.")
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="CSV file not found.")

    metadata_path = _metadata_path_for(csv_path)
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="CSV metadata not found.")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.setdefault("data_batch_id", None)
    return CSVFileDetails.model_validate(metadata)


def update_csv_metadata_batch_id(
    filename: str,
    data_batch_id: int,
    base_dir: Path = EXTRACT_DIR,
) -> None:
    base_path = base_dir.resolve()
    csv_path = (base_path / filename).resolve()
    if csv_path.parent != base_path:
        raise HTTPException(status_code=400, detail="Invalid CSV filename.")

    metadata_path = _metadata_path_for(csv_path)
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="CSV metadata not found.")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["data_batch_id"] = data_batch_id
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


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
