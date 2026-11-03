import os
from pathlib import Path

SOURCE_CODE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = SOURCE_CODE_DIR / "Output"
EXTRACT_DIR = OUTPUT_DIR
UPLOAD_DIR = OUTPUT_DIR / "uploads"
DEFAULT_MEDIA_TYPE = "text/csv"
PROCESSING_MANAGER_URL = os.getenv("PROCESSING_MANAGER_URL", "http://data-processing-manager:8002")
MYSQL_HOST = os.getenv("MYSQL_HOST", "data-processing-db")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "data_processing_db")
MYSQL_USER = os.getenv("MYSQL_USER", "dulari")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
