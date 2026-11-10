# File Management Converter API (File Manager)

A FastAPI service that accepts business data files (JSON, XML, XLS/XLSX, CSV, PDF, images), converts them to CSV,
registers them as a versioned **batch** in a shared MySQL database, and hands them to the **Data Processing Manager**
for validation. Rows that fail validation are quarantined; the user downloads them, corrects/reviews them, and
re-uploads the result as the next version.

Swagger UI: <http://localhost:8001/docs> · ReDoc: <http://localhost:8001/redoc> · OpenAPI JSON: <http://localhost:8001/openapi.json>

---

## 1. Workflow

```
 User ──► POST /upload ─────────────► convert to CSV ─► Output/<year>_<batch>_V<n>.csv
          (file + metadata)            original kept in Output/uploads/
                                       batch row saved in MySQL
   │
   ├─► GET  /files/{filename}/details      view metadata
   ├─► GET  /files/{filename}/content      download CSV
   │
   ├─► POST /files/{filename}/process ───► Data Processing Manager (:8002)
   │          │                             validates rows
   │          └─ quarantine_count > 0 ─► response contains `notification`
   │
   ├─► GET  /processing/batches/{id}/quarantine-export   download xport-quarantine.csv
   ├─► POST /processing/quarantine/{qid}/review          confirm | release | keep_quarantined
   └─► POST /processing/batches/{id}/reupload?current_version=N   reviewed CSV becomes version N+1
                                          └─► process again (loop until quarantine_count = 0)
```

Step by step:

1. **Upload** – client sends the file with `file_type`, `data_category`, `supplier_name`, `country`, `year`, `batch_name`
   (and optional `version`). The extension must match `file_type`.
2. **Duplicate check** – SHA hash of the bytes. Same file already uploaded → `409` with the existing file's details.
   A *different* file using the same year + batch name + version → `409`.
3. **Convert** – the matching converter produces a CSV named `{year}_{batch_name}_V{version}.csv`.
4. **Persist** – original saved to `Source code/Output/uploads/`, CSV to `Source code/Output/`, batch/supplier recorded in MySQL.
5. **Process** – File Manager creates/looks up the batch and calls the Data Processing Manager.
6. **Quarantine loop** – invalid rows are exported to `xport-quarantine.csv`; user reviews and re-uploads as `version + 1`.

---

## 2. Components

| Path | Responsibility |
|---|---|
| [Source code/app/main.py](<Source code/app/main.py>) | FastAPI app (title, description), includes router, ensures DB schema on startup. |
| [Source code/app/routes.py](<Source code/app/routes.py>) | All HTTP endpoints and Swagger metadata. |
| [Source code/app/schemas.py](<Source code/app/schemas.py>) | Pydantic models/enums: `FileType`, `DataCategory`, `UploadResponse`, `CSVFileDetails(Response)`, `ProcessingJobRequest`, `QuarantineReviewRequest`, `QuarantineNotification`. |
| [Source code/app/upload_service.py](<Source code/app/upload_service.py>) | `UploadService`: validation, dedupe by hash, version handling, conversion, saving files and batch, restoring CSV from original upload. |
| [Source code/app/manager.py](<Source code/app/manager.py>) | File hash, CSV metadata loading (`load_csv_metadata`), processing plan resolution. |
| [Source code/app/database.py](<Source code/app/database.py>) | MySQL access: connection check, schema/column migrations, `ensure_supplier_and_batch`, lookups by filename/hash/output name. |
| [Source code/app/processing_manager_client.py](<Source code/app/processing_manager_client.py>) | Async `httpx` client for the Data Processing Manager (process, quarantine export, review, re-upload). Errors → `502`. |
| [Source code/app/config.py](<Source code/app/config.py>) | Env-driven settings and output directories. |
| [Source code/Extract/](<Source code/Extract>) | Readers (`base_reader`, `json_reader`, `xml_reader`, `pdf_reader`) that parse raw input. |
| [Source code/convert/](<Source code/convert>) | Converters to CSV: `json`, `xml`, `excel` (xls/xlsx), `pdf` (pdfplumber), `image` (jpg/jpeg/png/gif/webp); shared helpers in `base_converter.py` (flattening, CSV writing). |
| `Source code/Output/` | Generated CSVs; `Output/uploads/` holds original uploads. |
| `Dockerfile`, `compose.yaml`, `Makefile`, `.env.example`, `requirements.txt` | Packaging and run configuration. |
| `SRC test/` | Tests (pytest). |

Supported inputs: `json, xml, csv, xls, xlsx, pdf, jpg, jpeg, png, gif, webp`.
Data categories: `financial`, `company`.

---

## 3. Requirements

- Python 3.14 (Docker image `python:3.14-slim`)
- MySQL (shared `data_processing_db`) reachable from the service
- Data Processing Manager running (default port 8002)
- Python packages (`requirements.txt`): `fastapi`, `uvicorn[standard]`, `python-multipart`, `httpx`,
  `mysql-connector-python`, `pdfplumber`, `pandas`, `openpyxl`, `xlrd`, `pytest`

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `MYSQL_HOST` | `data-processing-db` | MySQL host |
| `MYSQL_PORT` | `3306` | MySQL port |
| `MYSQL_DATABASE` | `data_processing_db` | Database name |
| `MYSQL_USER` | `dulari` (set `dpm_app` in `.env.example`) | DB user |
| `MYSQL_PASSWORD` | empty | DB password |
| `PROCESSING_MANAGER_URL` | `http://data-processing-manager:8002` | Data Processing Manager base URL |

Copy `.env.example` to `.env` and fill in values. Never commit `.env`.

---

## 4. Run

**Docker** (needs the external network `data_processing_net`):

```powershell
docker network create data_processing_net   # once
docker compose up --build
```

**Local (Windows)**:

```powershell
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
$env:PROCESSING_MANAGER_URL = "http://127.0.0.1:8002"
$env:PYTHONPATH = "Source code"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir "Source code" --host 127.0.0.1 --port 8001 --reload
```

Tests: `pytest`

---

## 5. API Reference (Swagger / OpenAPI)

All endpoints are tagged **File Manager** in Swagger UI.

### `GET /health` *(hidden from Swagger)*
Liveness probe → `{"status": "ok"}`.

### `GET /health/db` — Check the database connection
- `200` `{"status": "ok", "database": "connected"}`
- `503` database unavailable

### `POST /upload` — Upload a file and convert it to CSV
`multipart/form-data`

| Field | In | Type | Required | Notes |
|---|---|---|---|---|
| `file` | form | file | yes | Extension must equal `file_type` |
| `file_type` | form | enum `FileType` | yes | json, xml, xls, xlsx, csv, pdf, jpg, jpeg, png, gif, webp |
| `data_category` | form | enum | yes | financial, company |
| `supplier_name` | form | string | yes | Letters/digits style identifier (validated) |
| `country` | form | string | yes | |
| `year` | form | int | yes | 1901–2155 |
| `batch_name` | form | string | yes | Validated identifier |
| `version` | query | string | no | e.g. `v1` or `1` |

Response `UploadResponse`:

```json
{
  "message": "...",
  "output_file": "2026_batchA_V1.csv",
  "original_filename": "data.xlsx",
  "file_hash": "<hash>",
  "data_batch_id": 42,
  "file_type": "xlsx",
  "data_category": "financial",
  "country": "India",
  "year": 2026,
  "batch_name": "batchA"
}
```

Status codes: `200` CSV saved/converted · `201` created · `400` missing filename ·
`409` duplicate file (body = existing details) or year/batch/version already used by another file ·
`415` unsupported type · `422` extension mismatch, invalid identifier/version or conversion error · `502` database error.

### `GET /files/{filename}/details` — Get CSV file details
Returns `CSVFileDetailsResponse`: `filename, original_filename, data_batch_id, file_hash, file_type, data_category, country, year, batch_name, csv_path`.
Errors: `400` invalid filename · `404` not found · `422` bad batch name · `502` DB error.

### `GET /files/{filename}/content` — Download CSV content
Returns `text/csv` (`FileResponse`). If the CSV is missing it is rebuilt from the original upload; otherwise `404`.

### `POST /files/{filename}/process` — Process CSV
Body `ProcessingJobRequest`:

```json
{ "supplier_name": "Acme Ltd", "country": "India" }
```

Registers/updates the batch (version parsed from the filename suffix `_Vn`, default 1), then calls the Data Processing Manager.
Response (when rows are quarantined):

```json
{
  "data_batch_id": 42,
  "quarantine_count": 1,
  "notification": {
    "message": "Quarantine records require correction and review.",
    "data_batch_id": 42,
    "filename": "xport-quarantine.csv",
    "download_url": "/processing/batches/42/quarantine-export",
    "next_step": "Download the quarantine CSV, correct the rows, review them, and re-upload the next version."
  }
}
```

Errors: `404` file/metadata not found · `422` incomplete batch metadata · `502` Data Processing Manager or DB unavailable.

### `GET /processing/batches/{data_batch_id}/quarantine-export` — Download quarantine CSV
Proxies the Data Processing Manager; returns `text/csv` (`xport-quarantine.csv`).
Errors: `404` batch not found · `502` manager unavailable.

### `POST /processing/quarantine/{quarantine_id}/review` — Review a quarantined row
Body `QuarantineReviewRequest`:

```json
{ "decision": "confirm", "reason": "Value verified with supplier" }
```

`decision` ∈ `confirm` (row is valid) · `release` (remove from quarantine) · `keep_quarantined`. `reason` optional.
Errors: `404` row not found · `422` invalid body · `502` manager unavailable.

### `POST /processing/batches/{data_batch_id}/reupload` — Re-upload reviewed CSV
`multipart/form-data`: `file` (CSV only) and query `current_version` (int ≥ 1).
The new version sent downstream is `current_version + 1`.
Errors: `404` batch not found · `422` not a `.csv` / invalid version · `502` manager unavailable.

---

## 6. Typical session (curl)

```bash
curl -X POST "http://localhost:8001/upload?version=v1" \
  -F file=@data.xlsx -F file_type=xlsx -F data_category=financial \
  -F supplier_name=Acme -F country=India -F year=2026 -F batch_name=batchA

curl -X POST http://localhost:8001/files/2026_batchA_V1.csv/process \
  -H "Content-Type: application/json" -d '{"supplier_name":"Acme","country":"India"}'

curl -o xport-quarantine.csv http://localhost:8001/processing/batches/42/quarantine-export

curl -X POST http://localhost:8001/processing/quarantine/7/review \
  -H "Content-Type: application/json" -d '{"decision":"confirm"}'

curl -X POST "http://localhost:8001/processing/batches/42/reupload?current_version=1" -F file=@xport-quarantine.csv
```
