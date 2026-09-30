from fastapi import FastAPI

from app.routes import router

app = FastAPI(
    title="File Management Converter API",
    version="1.0.0",
    description=(
        "Upload a file, declare its file type and sub-type, provide business metadata "
        "such as data category, year, and batch name, and route the job through the file manager."
    ),
)

app.include_router(router)
