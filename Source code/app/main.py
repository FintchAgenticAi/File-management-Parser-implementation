import logging

from fastapi import FastAPI

from app.database import DatabaseError, ensure_schema
from app.routes import router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="File Management Converter API",
    version="1.0.0",
    description=(
        "Upload and process files through the File Manager. When the Data Processing Manager "
        "finds invalid rows, download xport-quarantine.csv, review each row, confirm or release "
        "it, and re-upload the reviewed CSV as the next version."
    ),
)

app.include_router(router)


@app.on_event("startup")
def prepare_database() -> None:
    try:
        ensure_schema()
    except DatabaseError:
        logger.exception("Database schema check failed at startup")
