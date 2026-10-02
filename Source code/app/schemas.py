from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class FileType(str, Enum):
    json = "json"
    xml = "xml"
    csv = "csv"
    xlsx = "xlsx"
    pdf = "pdf"
    jpg = "jpg"
    jpeg = "jpeg"
    png = "png"
    gif = "gif"
    webp = "webp"


class DataCategory(str, Enum):
    financial = "financial"
    company = "company"


class FileProcessingContext(BaseModel):
    file_type: FileType = Field(..., description="Top-level file type to convert or process.")
    data_category: DataCategory = Field(..., description="Business category for the uploaded file.")
    country: str = Field(..., min_length=1, description="Country associated with the uploaded file.")
    year: int = Field(..., ge=1900, le=2100, description="Business year for the file batch.")
    batch_name: str = Field(..., min_length=1, description="Name of the batch to attach to the processing job.")


class UploadResponse(BaseModel):
    message: str
    output_file: str
    file_hash: str
    file_type: FileType
    data_category: DataCategory
    country: str | None = None
    year: int
    batch_name: str


class CSVFileDetails(BaseModel):
    filename: str
    original_filename: str
    processor: str | None = None
    file_hash: str | None = None
    file_type: FileType
    data_category: DataCategory
    country: str | None = None
    year: int
    batch_name: str
    csv_path: str


class CSVIncludedDetails(BaseModel):
    columns: list[str]
    row_count: int
    rows: list[dict[str, str]]


class ProcessingManagerPayload(BaseModel):
    event: Literal["csv_ready_for_processing"]
    csv_file: CSVFileDetails
    included_details: CSVIncludedDetails


class ProcessingJobRequest(BaseModel):
    supplier_name: str = Field(..., min_length=1, description="Supplier or company name for the processing job.")
    country: str = Field(..., min_length=1, description="Country associated with the processing job.")


class QuarantineReviewRequest(BaseModel):
    decision: Literal["confirm", "release", "keep_quarantined"] = Field(
        ...,
        description="Review action: confirm a valid row, release it from quarantine, or keep it quarantined.",
    )
    reason: str | None = Field(default=None, description="Optional explanation for the review decision.")


class QuarantineNotification(BaseModel):
    message: str = Field(..., description="Notification shown to the user.")
    data_batch_id: int = Field(..., description="Processing batch containing quarantined rows.")
    filename: str = Field("xport-quarantine.csv", description="CSV file the user downloads for review.")
    download_url: str = Field(..., description="File Manager endpoint used to download the quarantine CSV.")
