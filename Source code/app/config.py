from pathlib import Path

SOURCE_CODE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = SOURCE_CODE_DIR / "Output"
EXTRACT_DIR = OUTPUT_DIR
UPLOAD_DIR = OUTPUT_DIR / "uploads"
DEFAULT_MEDIA_TYPE = "text/csv"
