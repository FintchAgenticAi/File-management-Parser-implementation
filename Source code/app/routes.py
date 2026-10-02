from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse

from app.config import EXTRACT_DIR
from app.manager import load_csv_metadata
from app.schemas import CSVFileDetails, DataCategory, FileType, UploadResponse
from app.upload_service import UploadService

router = APIRouter()


def _get_converter(filename: str):
    return upload_service.converter_resolver(filename)


upload_service = UploadService(extract_dir=EXTRACT_DIR)


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
