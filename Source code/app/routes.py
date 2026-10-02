from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse

from app.config import EXTRACT_DIR, PROCESSING_MANAGER_URL
from app.manager import load_csv_included_details, load_csv_metadata
from app.schemas import (
    CSVFileDetails,
    DataCategory,
    FileType,
    ProcessingManagerPayload,
    ProcessingJobRequest,
    QuarantineNotification,
    QuarantineReviewRequest,
    UploadResponse,
)
from app.processing_manager_client import ProcessingManagerClient
from app.upload_service import UploadService

router = APIRouter()


def _get_converter(filename: str):
    return upload_service.converter_resolver(filename)


upload_service = UploadService(extract_dir=EXTRACT_DIR)
processing_manager = ProcessingManagerClient(PROCESSING_MANAGER_URL)


@router.get("/health", include_in_schema=False)
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/upload",
    tags=["File Manager"],
    status_code=201,
    response_description="Created",
    responses={
        200: {"description": "OK - CSV file saved directly"},
        201: {"description": "Created"},
        409: {"description": "Conflict - file already uploaded"},
    },
    summary="Upload a file and convert it to CSV",
    description=(
        "Upload a file plus metadata so Swagger shows the supported input formats and converts them to CSV."
    ),
    response_model=UploadResponse,
)
async def upload_file(
    response: Response,
    version: str | None = Query(default=None, description="Batch version. Enter any version string such as v1"),
    file: UploadFile = File(..., description="The source file to convert into CSV."),
    file_type: FileType = Form(..., description="Input file format to convert: json, xml, xlsx, csv, pdf, jpg, jpeg, png, gif, or webp."),
    data_category: DataCategory = Form(..., description="Business category for the uploaded file."),
    country: str = Form(..., description="Country associated with the uploaded file."),
    year: int = Form(..., ge=1900, le=2100, description="Business year for the data."),
    batch_name: str = Form(..., description="Batch name for grouping the data."),
) -> UploadResponse:
    upload_service.extract_dir = EXTRACT_DIR
    return await upload_service.process_upload(
        response=response,
        version=version,
        file=file,
        file_type=file_type,
        data_category=data_category,
        country=country,
        year=year,
        batch_name=batch_name,
        converter_resolver=_get_converter,
        extract_dir=EXTRACT_DIR,
    )


@router.get(
    "/files/{filename}/details",
    tags=["File Manager"],
    response_model=CSVFileDetails,
    summary="Get CSV file details",
    description="Returns the metadata created when File Manager converted or stored the CSV.",
)
def get_csv_file_details(filename: str) -> CSVFileDetails:
    return load_csv_metadata(filename, base_dir=EXTRACT_DIR)


@router.post(
    "/files/{filename}/send-to-processing-manager",
    tags=["File Manager"],
    response_model=ProcessingManagerPayload,
    summary="Send CSV details to the data processing manager",
    description=(
        "Builds the payload for the data processing manager. It includes the stored CSV "
        "metadata and every CSV row keyed by its column name."
    ),
)
def send_csv_to_processing_manager(filename: str) -> ProcessingManagerPayload:
    csv_file = load_csv_metadata(filename, base_dir=EXTRACT_DIR)
    included_details = load_csv_included_details(filename, base_dir=EXTRACT_DIR)
    return ProcessingManagerPayload(
        event="csv_ready_for_processing",
        csv_file=csv_file,
        included_details=included_details,
    )


@router.get(
    "/files/{filename}/content",
    tags=["File Manager"],
    response_class=FileResponse,
    summary="Download CSV file content",
    description="Returns the CSV content for downstream processing services.",
)
def download_csv_file(filename: str) -> FileResponse:
    details = load_csv_metadata(filename, base_dir=EXTRACT_DIR)
    csv_path = EXTRACT_DIR / details.filename
    if not csv_path.is_file():
        raise HTTPException(status_code=404, detail="CSV file not found.")
    return FileResponse(csv_path, media_type="text/csv", filename=csv_path.name)


@router.post(
    "/files/{filename}/process",
    tags=["File Manager"],
    summary="Send a CSV to the Data Processing Manager",
    description=(
        "Starts processing for a stored CSV. If invalid rows are found, the response includes "
        "a notification with the xport-quarantine.csv download URL and data batch ID."
    ),
    responses={
        200: {
            "description": "Processing result. A notification is included when rows are quarantined.",
            "content": {
                "application/json": {
                    "example": {
                        "data_batch_id": 42,
                        "quarantine_count": 1,
                        "notification": {
                            "message": "Quarantine records require review.",
                            "data_batch_id": 42,
                            "filename": "xport-quarantine.csv",
                            "download_url": "/processing/batches/42/quarantine-export",
                        },
                    }
                }
            },
        },
        404: {"description": "CSV file or metadata was not found."},
        502: {"description": "Data Processing Manager is unavailable."},
    },
)
async def process_csv_from_file_manager(
    filename: str,
    request: ProcessingJobRequest,
) -> dict[str, object]:
    details = load_csv_metadata(filename, base_dir=EXTRACT_DIR)
    result = await processing_manager.process_csv(details.filename, request.supplier_name, request.country)
    if int(result.get("quarantine_count", 0)) > 0:
        batch_id = int(result["data_batch_id"])
        result["notification"] = QuarantineNotification(
            message="Quarantine records require review.",
            data_batch_id=batch_id,
            filename="xport-quarantine.csv",
            download_url=f"/processing/batches/{batch_id}/quarantine-export",
        ).model_dump()
    return result


@router.get(
    "/processing/batches/{data_batch_id}/quarantine-export",
    tags=["File Manager"],
    response_class=Response,
    summary="Download quarantine export through File Manager",
    description=(
        "Downloads xport-quarantine.csv for the specified processing batch. "
        "Use the data_batch_id from the processing notification."
    ),
    responses={
        200: {
            "description": "CSV quarantine export.",
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
        },
        404: {"description": "Processing batch was not found."},
        502: {"description": "Data Processing Manager is unavailable."},
    },
)
async def download_processing_quarantine_export(data_batch_id: int) -> Response:
    response = await processing_manager.download_quarantine_export(data_batch_id)
    return Response(
        content=response.content,
        media_type="text/csv",
        headers={
            "Content-Disposition": response.headers.get(
                "content-disposition",
                'attachment; filename="xport-quarantine.csv"',
            )
        },
    )


@router.post(
    "/processing/quarantine/{quarantine_id}/review",
    tags=["File Manager"],
    summary="Confirm or release a quarantined row through File Manager",
    description=(
        "Submit the user's decision for one quarantined row. Use confirm for a valid row, "
        "release to remove it from quarantine, or keep_quarantined when it still needs review."
    ),
    responses={
        200: {"description": "Quarantine row review was accepted."},
        422: {"description": "Invalid decision or request body."},
        404: {"description": "Quarantined row was not found."},
        502: {"description": "Data Processing Manager is unavailable."},
    },
)
async def review_processing_quarantine(
    quarantine_id: int,
    request: QuarantineReviewRequest,
) -> dict[str, object]:
    return await processing_manager.review_quarantine(quarantine_id, request.model_dump())


@router.post(
    "/processing/batches/{data_batch_id}/reupload",
    tags=["File Manager"],
    summary="Re-upload a reviewed CSV as the next version",
    description=(
        "Uploads the reviewed xport-quarantine.csv file. The File Manager calculates the next "
        "version as current_version + 1 and sends that version to the Data Processing Manager."
    ),
    responses={
        200: {"description": "Reviewed CSV accepted as the next version."},
        422: {"description": "Only CSV files are accepted, or current_version is invalid."},
        404: {"description": "Processing batch was not found."},
        502: {"description": "Data Processing Manager is unavailable."},
    },
)
async def reupload_processing_csv(
    data_batch_id: int,
    current_version: int = Query(..., ge=1, description="Current CSV version. The uploaded file becomes this version plus one."),
    file: UploadFile = File(...),
) -> dict[str, object]:
    if not file.filename or file.filename.lower().split(".")[-1] != "csv":
        raise HTTPException(status_code=422, detail="Only CSV files can be re-uploaded.")
    return await processing_manager.reupload_csv(data_batch_id, file, next_version=current_version + 1)
