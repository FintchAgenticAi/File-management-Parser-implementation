import os
from pathlib import Path

SOURCE_CODE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = SOURCE_CODE_DIR / "Output"
EXTRACT_DIR = OUTPUT_DIR
UPLOAD_DIR = OUTPUT_DIR / "uploads"
DEFAULT_MEDIA_TYPE = "text/csv"
PROCESSING_MANAGER_URL = os.getenv("PROCESSING_MANAGER_URL", "http://127.0.0.1:8001")
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3307"))
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "data_processing_db")
MYSQL_USER = os.getenv("MYSQL_USER", "dulari")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
