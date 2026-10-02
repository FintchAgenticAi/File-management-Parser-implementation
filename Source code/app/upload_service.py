from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, Response, UploadFile

from app.config import EXTRACT_DIR, UPLOAD_DIR
from app.manager import (
    compute_file_hash,
    find_existing_csv_details_by_hash,
    resolve_processing_plan,
    store_csv_metadata,
)
from app.schemas import (
    CSVFileDetails,
    DataCategory,
    FileProcessingContext,
    FileType,
    UploadResponse,
)
from Extract.base_reader import ReaderError


class UploadService:
    def __init__(
        self,
        extract_dir: Path = EXTRACT_DIR,
        converter_resolver: Callable[[str], Callable[[Path], Path]] | None = None,
    ) -> None:
        self.extract_dir = extract_dir
        self.upload_dir = UPLOAD_DIR
        self.converter_resolver = converter_resolver or self._default_converter_resolver

    async def process_upload(
        self,
        response: Response,
        version: str | None,
        file: UploadFile,
        file_type: FileType,
        data_category: DataCategory,
        country: str,
        year: int,
        batch_name: str,
        converter_resolver: Callable[[str], Callable[[Path], Path]] | None = None,
        extract_dir: Path | None = None,
    ) -> UploadResponse:
        if not file.filename:
            raise HTTPException(status_code=400, detail="A filename is required.")

        if extract_dir is not None:
            self.extract_dir = extract_dir

        file_bytes = await file.read()
        file_hash = compute_file_hash(file_bytes)
        input_suffix = Path(file.filename).suffix.lower()

        self._save_original_upload(file.filename, file_bytes, year, batch_name, version)

        existing_details = find_existing_csv_details_by_hash(file_hash, base_dir=self.extract_dir)
        if existing_details is not None:
            response.status_code = 409
            return self._build_response_from_details(existing_details)

        if input_suffix == ".csv":
            return self._save_csv_file(response, file, file_bytes, file_hash, file_type, data_category, country, year, batch_name, version)

        return await self._convert_and_store_file(
            response,
            file,
            file_bytes,
            file_hash,
            file_type,
            data_category,
            country,
            year,
            batch_name,
            version,
            converter_resolver=converter_resolver,
        )

    def _save_csv_file(
        self,
        response: Response,
        file: UploadFile,
        file_bytes: bytes,
        file_hash: str,
        file_type: FileType,
        data_category: DataCategory,
        country: str,
        year: int,
        batch_name: str,
        version: str | None,
    ) -> UploadResponse:
        context = self._build_context(file_type, data_category, country, year, batch_name)
        self.extract_dir.mkdir(parents=True, exist_ok=True)
        csv_path = self._build_output_path(year, batch_name, version)
        csv_path.write_bytes(file_bytes)

        store_csv_metadata(csv_path, file.filename, context, "file_manager", file_hash)
        response.status_code = 200
        return self._build_processing_response(
            message="file already csv, saved directly",
            output_file=csv_path.name,
            context=context,
            file_hash=file_hash,
        )

    async def _convert_and_store_file(
        self,
        response: Response,
        file: UploadFile,
        file_bytes: bytes,
        file_hash: str,
        file_type: FileType,
        data_category: DataCategory,
        country: str,
        year: int,
        batch_name: str,
        version: str | None,
        converter_resolver: Callable[[str], Callable[[Path], Path]] | None = None,
    ) -> UploadResponse:
        context = self._build_context(file_type, data_category, country, year, batch_name)
        processing_plan = resolve_processing_plan(file.filename, context)
        self.extract_dir.mkdir(parents=True, exist_ok=True)

        effective_converter_resolver = converter_resolver or self.converter_resolver
        converter = effective_converter_resolver(file.filename)
        suffix = Path(file.filename).suffix.lower() or ".bin"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(file_bytes)
            temp_path = Path(temp_file.name)

        try:
            csv_path = converter(temp_path, output_dir=self.extract_dir)
            target_path = self._build_output_path(year, batch_name, version)
            if csv_path.exists() and csv_path != target_path:
                csv_path.replace(target_path)
                csv_path = target_path
        except ReaderError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            temp_path.unlink(missing_ok=True)

        store_csv_metadata(csv_path, file.filename, context, processing_plan["processor"], file_hash)
        response.status_code = 201
        return self._build_processing_response(
            message="file converted successfully",
            output_file=csv_path.name,
            context=context,
            file_hash=file_hash,
        )

    def _build_context(self, file_type: FileType, data_category: DataCategory, country: str, year: int, batch_name: str) -> FileProcessingContext:
        return FileProcessingContext(
            file_type=file_type,
            data_category=data_category,
            country=country,
            year=year,
            batch_name=batch_name,
        )

    def _build_output_path(self, year: int, batch_name: str, version: str | None) -> Path:
        version_suffix = f"_{version}" if version else ""
        return self.extract_dir / f"{year}_{batch_name}{version_suffix}.csv"

    def _save_original_upload(
        self,
        original_filename: str,
        file_bytes: bytes,
        year: int,
        batch_name: str,
        version: str | None,
    ) -> Path:
        self.extract_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        safe_name = Path(original_filename).name
        version_suffix = f"_{version}" if version else ""
        file_suffix = Path(safe_name).suffix.lower() or ".bin"
        uploaded_path = self.upload_dir / f"{year}_{batch_name}{version_suffix}{file_suffix}"
        uploaded_path.write_bytes(file_bytes)
        return uploaded_path

    def _build_response_from_details(self, details: CSVFileDetails) -> UploadResponse:
        return UploadResponse(
            message="uploaded this file before",
            output_file=details.filename,
            file_hash=details.file_hash or "",
            file_type=details.file_type,
            data_category=details.data_category,
            country=details.country,
            year=details.year,
            batch_name=details.batch_name,
        )

    def _build_processing_response(
        self,
        message: str,
        output_file: str,
        context: FileProcessingContext,
        file_hash: str,
    ) -> UploadResponse:
        return UploadResponse(
            message=message,
            output_file=output_file,
            file_hash=file_hash,
            file_type=context.file_type,
            data_category=context.data_category,
            country=context.country,
            year=context.year,
            batch_name=context.batch_name,
        )

    def _default_converter_resolver(self, filename: str) -> Callable[[Path], Path]:
        suffix = Path(filename).suffix.lower()
        converter_map = {
            ".json": self._json_converter,
            ".xml": self._xml_converter,
            ".xlsx": self._excel_converter,
            ".pdf": self._pdf_converter,
            ".jpg": lambda temp_path, output_dir: self._image_converter(temp_path, output_dir, original_filename=filename),
            ".jpeg": lambda temp_path, output_dir: self._image_converter(temp_path, output_dir, original_filename=filename),
            ".png": lambda temp_path, output_dir: self._image_converter(temp_path, output_dir, original_filename=filename),
            ".gif": lambda temp_path, output_dir: self._image_converter(temp_path, output_dir, original_filename=filename),
            ".webp": lambda temp_path, output_dir: self._image_converter(temp_path, output_dir, original_filename=filename),
        }
        if suffix not in converter_map:
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {suffix}")
        return converter_map[suffix]

    def _json_converter(self, temp_path: Path, output_dir: Path) -> Path:
        from convert.json_converter import convert_json_to_csv
        return convert_json_to_csv(temp_path, output_dir=output_dir)

    def _xml_converter(self, temp_path: Path, output_dir: Path) -> Path:
        from convert.xml_converter import convert_xml_to_csv
        return convert_xml_to_csv(temp_path, output_dir=output_dir)

    def _excel_converter(self, temp_path: Path, output_dir: Path) -> Path:
        from convert.excel_converter import convert_excel_to_csv
        return convert_excel_to_csv(temp_path, output_dir=output_dir)

    def _pdf_converter(self, temp_path: Path, output_dir: Path) -> Path:
        from convert.pdf_converter import convert_pdf_to_csv
        return convert_pdf_to_csv(temp_path, output_dir=output_dir)

    def _image_converter(self, temp_path: Path, output_dir: Path, original_filename: str | None = None) -> Path:
        from convert.image_converter import convert_image_to_csv

        return convert_image_to_csv(temp_path, output_dir=output_dir, original_filename=original_filename)
