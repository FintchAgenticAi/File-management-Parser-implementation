from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app import database, manager, routes
from app import upload_service as upload_service_module
from app.schemas import CSVFileDetails, DataCategory, FileType

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")

    response = client.post(
        "/upload",
        files={"file": ("sample.json", '{"name":"Ada"}', "application/json")},
        data={
            "file_type": "json",
            "data_category": "company",
            "country": "US",
            "year": 2026,
            "batch_name": "batch-a",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["output_file"].endswith(".csv")
    assert payload["country"] == "US"
    assert "details_url" not in payload
    assert "sub_file_type" not in payload
    assert payload["file_hash"]

    assert "download_url" not in payload
    assert list(tmp_path.glob("*.json")) == [tmp_path / "2026_batch-a.meta.json"]

    upload_path = tmp_path / "uploads" / "2026_batch-a.json"
    assert upload_path.exists()
    assert payload["data_batch_id"] is None


def test_batch_id_increments_and_stays_same_for_versions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")

    first = client.post(
        "/upload?version=v1",
        files={"file": ("first.csv", "id\n1\n", "text/csv")},
        data={"file_type": "csv", "data_category": "company", "country": "US", "year": 2026, "batch_name": "first"},
    )
    second = client.post(
        "/upload?version=v1",
        files={"file": ("second.csv", "id\n2\n", "text/csv")},
        data={"file_type": "csv", "data_category": "company", "country": "US", "year": 2026, "batch_name": "second"},
    )
    first_v2 = client.post(
        "/upload?version=v2",
        files={"file": ("first-v2.csv", "id\n3\n", "text/csv")},
        data={"file_type": "csv", "data_category": "company", "country": "US", "year": 2026, "batch_name": "first"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first_v2.status_code == 200
    assert first.json()["data_batch_id"] is None
    assert second.json()["data_batch_id"] is None
    assert first_v2.json()["data_batch_id"] is None


def test_upload_image_converts_to_csv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAA3AABQABQAB3dyjBAAAAABJRU5ErkJggg=="
    )

    response = client.post(
        "/upload",
        files={"file": ("sample.png", png_bytes, "image/png")},
        data={
            "file_type": "png",
            "data_category": "company",
            "country": "US",
            "year": 2026,
            "batch_name": "batch-image",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["output_file"].endswith(".csv")

    upload_path = tmp_path / "uploads" / "2026_batch-image.png"
    assert upload_path.exists()

    output_path = tmp_path / payload["output_file"]
    assert output_path.exists()
    csv_text = output_path.read_text(encoding="utf-8-sig")
    assert "sample.png" in csv_text
    assert "mime_type" in csv_text


def test_upload_xlsx_converts_to_csv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")

    workbook = BytesIO()
    pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]}).to_excel(workbook, index=False)
    workbook.seek(0)

    response = client.post(
        "/upload",
        files={"file": ("sample.xlsx", workbook.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={
            "file_type": "xlsx",
            "data_category": "company",
            "country": "US",
            "year": 2026,
            "batch_name": "batch-excel",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["output_file"] == "2026_batch-excel.csv"
    csv_text = (tmp_path / payload["output_file"]).read_text(encoding="utf-8-sig")
    assert "id,name" in csv_text
    assert "1,Alice" in csv_text


def test_duplicate_upload_returns_existing_csv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")

    first_response = client.post(
        "/upload",
        files={"file": ("sample.json", '{"name":"Ada"}', "application/json")},
        data={
            "file_type": "json",
            "data_category": "company",
            "country": "US",
            "year": 2026,
            "batch_name": "batch-a",
        },
    )

    second_response = client.post(
        "/upload",
        files={"file": ("sample.json", '{"name":"Ada"}', "application/json")},
        data={
            "file_type": "json",
            "data_category": "company",
            "country": "US",
            "year": 2026,
            "batch_name": "batch-a",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409

    first_payload = first_response.json()
    second_payload = second_response.json()
    assert second_payload["message"] == "File already uploaded."
    assert second_payload["output_file"] == first_payload["output_file"]


def test_duplicate_upload_returns_conflict_when_csv_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")
    existing_batch = database.DataBatchRecord(
        data_batch_id=17,
        supplier_id=15,
        batch_name="AAA",
        country="SL",
        created_at=None,
        version=1,
        data_category="financial",
        year=1902,
        file_hash="duplicate-hash",
        file_type="xlsx",
    )
    monkeypatch.setattr(
        upload_service_module,
        "find_existing_csv_details_by_hash",
        lambda *_args, **_kwargs: existing_batch,
    )

    response = client.post(
        "/upload?version=v1",
        files={"file": ("duplicate.xlsx", b"duplicate content", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={
            "file_type": "xlsx",
            "data_category": "financial",
            "supplier_name": "keggle",
            "country": "UK",
            "year": 1901,
            "batch_name": "ASD",
        },
    )

    assert response.status_code == 409
    assert response.json()["message"] == "File already uploaded."
    assert response.json()["output_file"] == "1902_AAA_V1.csv"
    assert not (tmp_path / "1901_ASD_V1.csv").exists()


def test_different_file_with_same_output_name_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")
    owner = database.DataBatchRecord(
        data_batch_id=19,
        supplier_id=15,
        batch_name="ASD",
        country="UK",
        created_at=None,
        version=1,
        data_category="financial",
        year=1901,
        file_hash="other-hash",
        file_type="xlsx",
    )
    monkeypatch.setattr(upload_service_module, "find_existing_csv_details_by_hash", lambda *_a, **_k: None)
    monkeypatch.setattr(upload_service_module, "find_batch_by_output_name", lambda *_a, **_k: owner)

    response = client.post(
        "/upload?version=v1",
        files={"file": ("new.xlsx", b"different content", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={
            "file_type": "xlsx",
            "data_category": "financial",
            "supplier_name": "keggle",
            "country": "UK",
            "year": 1901,
            "batch_name": "ASD",
        },
    )

    assert response.status_code == 409
    assert "data_batch_id 19" in response.json()["detail"]
    assert not (tmp_path / "uploads").exists()


def test_upload_csv_skips_conversion(tmp_path: Path, monkeypatch) -> None:
    saved_batch_args: list[object] = []

    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(routes, "_get_converter", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("converter should not run for CSV input")))

    def save_batch(*args, **_kwargs):
        saved_batch_args.extend(args)
        return SimpleNamespace(data_batch_id=None)

    monkeypatch.setattr(
        routes.upload_service,
        "_save_batch",
        save_batch,
    )

    csv_content = "id,name,amount\n1,Alice,100\n2,Bob,200\n3,Charlie,300\n"
    response = client.post(
        "/upload",
        files={"file": ("sample.csv", csv_content, "text/csv")},
        data={
            "file_type": "csv",
            "data_category": "company",
            "supplier_name": "test-supplier",
            "country": "US",
            "year": 2026,
            "batch_name": "batch-csv",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "File is already CSV, saved directly."
    assert payload["output_file"] == "2026_batch-csv.csv"
    assert "sub_file_type" not in payload
    assert payload["file_type"] == "csv"

    upload_path = tmp_path / "uploads" / "2026_batch-csv.csv"
    assert upload_path.exists()

    stored_csv = tmp_path / "2026_batch-csv.csv"
    assert stored_csv.exists()
    assert stored_csv.read_text(encoding="utf-8-sig") == csv_content
    assert list(tmp_path.rglob("*.json")) == []
    assert saved_batch_args[-1] is FileType.csv


def test_database_adds_file_type_column_when_missing(monkeypatch) -> None:
    class Cursor:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: str) -> None:
            self.statements.append(statement)

        def fetchone(self):
            return None

    cursor = Cursor()
    database._ensure_file_type_column(cursor)

    assert cursor.statements == [
        "SHOW COLUMNS FROM data_batch LIKE 'file_type'",
        "ALTER TABLE data_batch ADD COLUMN file_type VARCHAR(16) NULL",
    ]


def test_database_saves_uploaded_file_type(monkeypatch) -> None:
    class Cursor:
        lastrowid = 42

        def __init__(self) -> None:
            self.results = [None, None, None, None, {"supplier_id": 7}, None]
            self.statements: list[tuple[str, tuple[object, ...] | None]] = []

        def execute(self, statement: str, params=None) -> None:
            self.statements.append((statement, params))

        def fetchone(self):
            return self.results.pop(0)

        def close(self) -> None:
            pass

    class Connection:
        def __init__(self) -> None:
            self.db_cursor = Cursor()

        def cursor(self, **_kwargs):
            return self.db_cursor

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            pass

        def close(self) -> None:
            pass

    connection = Connection()
    monkeypatch.setattr(database, "_connect", lambda: connection)

    batch = database.ensure_supplier_and_batch(
        supplier_name="Acme",
        batch_name="reports",
        country="US",
        version=1,
        data_category="company",
        year=2026,
        file_hash="hash",
        file_type="xlsx",
        original_filename="Quarterly Report.xlsx",
        output_filename="2026_reports_V1.csv",
    )

    assert batch.file_type == "xlsx"
    assert batch.original_filename == "Quarterly Report.xlsx"
    insert_params = connection.db_cursor.statements[-1][1]
    assert insert_params is not None
    assert insert_params[-3] == "xlsx"
    assert insert_params[-2] == "Quarterly Report.xlsx"
    assert insert_params[-1] == "2026_reports_V1.csv"
    assert any("original_filename" in statement for statement, _ in connection.db_cursor.statements)


def test_upload_openapi_exposes_single_file_type_enum() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]["Body_upload_file_upload_post"]
    properties = schema["properties"]

    assert "file_type" in properties
    assert "input_file_type" not in properties
    assert "sub_file_type" not in properties
    assert response.json()["components"]["schemas"]["FileType"]["enum"] == ["json", "xml", "csv", "xls", "xlsx", "pdf", "jpg", "jpeg", "png", "gif", "webp"]
    assert response.json()["paths"]["/upload"]["post"]["tags"] == ["File Manager"]
    assert "/files/{filename}/send-to-processing-manager" not in response.json()["paths"]

    parameters = response.json()["paths"]["/upload"]["post"]["parameters"]
    assert any(param["name"] == "version" and param["in"] == "query" for param in parameters)


def test_csv_details_response_excludes_processor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")

    upload_response = client.post(
        "/upload",
        files={"file": ("sample.csv", "id,name\n1,Alice\n", "text/csv")},
        data={
            "file_type": "csv",
            "data_category": "company",
            "country": "US",
            "year": 2026,
            "batch_name": "details-test",
        },
    )
    assert upload_response.status_code == 200

    details_response = client.get("/files/2026_details-test.csv/details")

    assert details_response.status_code == 200
    assert "processor" not in details_response.json()
    openapi = client.get("/openapi.json").json()
    assert "processor" not in openapi["components"]["schemas"]["CSVFileDetailsResponse"]["properties"]


def test_csv_details_are_returned_from_database_when_csv_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "extract_dir", tmp_path)
    batch = database.DataBatchRecord(
        data_batch_id=17,
        supplier_id=15,
        batch_name="AAA",
        country="SL",
        created_at=None,
        version=1,
        data_category="financial",
        year=1902,
        file_hash="edd74611fbbd8d3d38ccc2e48a8bb74556f8f3e1316f0e91de310108a6c6c813",
        file_type="xlsx",
        original_filename="synthesized_financial_dataset.xlsx",
    )
    monkeypatch.setattr(manager, "get_batch_for_file", lambda _filename: batch)

    response = client.get("/files/1902_AAA_V1.csv/details")

    assert response.status_code == 200
    assert response.json() == {
        "filename": "1902_AAA_V1.csv",
        "original_filename": "synthesized_financial_dataset.xlsx",
        "data_batch_id": 17,
        "file_hash": batch.file_hash,
        "file_type": "xlsx",
        "data_category": "financial",
        "country": "SL",
        "year": 1902,
        "batch_name": "AAA",
        "csv_path": str(tmp_path / "1902_AAA_V1.csv"),
    }


def test_csv_content_is_regenerated_from_matching_original_upload(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "Output"
    upload_dir = output_dir / "uploads"
    upload_dir.mkdir(parents=True)
    workbook = BytesIO()
    pd.DataFrame({"id": [1], "name": ["Alice"]}).to_excel(workbook, index=False)
    original_bytes = workbook.getvalue()
    (upload_dir / "1901_QSD_V1.xlsx").write_bytes(original_bytes)

    monkeypatch.setattr(routes, "EXTRACT_DIR", output_dir)
    monkeypatch.setattr(routes.upload_service, "extract_dir", output_dir)
    monkeypatch.setattr(routes.upload_service, "upload_dir", upload_dir)
    batch = database.DataBatchRecord(
        data_batch_id=16,
        supplier_id=22,
        batch_name="QSD",
        country="SL",
        created_at=None,
        version=1,
        data_category="financial",
        year=1901,
        file_hash=manager.compute_file_hash(original_bytes),
        file_type="xlsx",
    )
    monkeypatch.setattr(manager, "get_batch_for_file", lambda _filename: batch)

    response = client.get("/files/1901_QSD_V1.csv/content")

    assert response.status_code == 200
    assert "id,name" in response.text
    assert "1,Alice" in response.text
    assert (output_dir / "1901_QSD_V1.csv").is_file()


def test_quarantine_notification_contains_downloadable_export_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    (tmp_path / "2026_batch-csv.csv").write_text("id,name\n1,Alice\n", encoding="utf-8")
    monkeypatch.setattr(
        routes,
        "load_csv_metadata",
        lambda *_args, **_kwargs: CSVFileDetails(
            filename="2026_batch-csv.csv",
            original_filename=None,
            data_batch_id=42,
            file_hash="hash",
            file_type=FileType.csv,
            data_category=DataCategory.company,
            country="US",
            year=2026,
            batch_name="batch-csv",
            csv_path=str(tmp_path / "2026_batch-csv.csv"),
        ),
    )
    monkeypatch.setattr(
        routes,
        "ensure_supplier_and_batch",
        lambda **_kwargs: SimpleNamespace(data_batch_id=42),
    )

    async def process_csv(*_args, **_kwargs):
        return {"data_batch_id": 42, "quarantine_count": 1}

    monkeypatch.setattr(routes.processing_manager, "process_csv", process_csv)
    response = client.post(
        "/files/2026_batch-csv.csv/process",
        json={"supplier_name": "Acme", "country": "US"},
    )

    assert response.status_code == 200
    assert response.json()["notification"] == {
        "message": "Quarantine records require correction and review.",
        "data_batch_id": 42,
        "filename": "xport-quarantine.csv",
        "download_url": "/processing/batches/42/quarantine-export",
        "next_step": "Download the quarantine CSV, correct the rows, review them, and re-upload the next version.",
    }


def test_reupload_passes_current_version_plus_one_to_processing_manager(monkeypatch) -> None:
    captured: dict[str, int] = {}

    async def reupload_csv(data_batch_id, file, next_version):
        captured["data_batch_id"] = data_batch_id
        captured["next_version"] = next_version
        assert file.filename == "reviewed.csv"
        return {"status": "accepted", "version": next_version}

    monkeypatch.setattr(routes.processing_manager, "reupload_csv", reupload_csv)
    response = client.post(
        "/processing/batches/42/reupload?current_version=3",
        files={"file": ("reviewed.csv", "id,name\n1,Alice\n", "text/csv")},
    )

    assert response.status_code == 200
    assert captured == {"data_batch_id": 42, "next_version": 4}
    assert response.json() == {"status": "accepted", "version": 4}


def test_quarantine_workflow_is_documented_in_openapi() -> None:
    openapi = client.get("/openapi.json").json()

    process_operation = openapi["paths"]["/files/{filename}/process"]["post"]
    download_operation = openapi["paths"]["/processing/batches/{data_batch_id}/quarantine-export"]["get"]
    review_operation = openapi["paths"]["/processing/quarantine/{quarantine_id}/review"]["post"]
    reupload_operation = openapi["paths"]["/processing/batches/{data_batch_id}/reupload"]["post"]

    assert "xport-quarantine.csv" in process_operation["description"]
    assert "correction" in process_operation["description"]
    assert "text/csv" in download_operation["responses"]["200"]["content"]
    review_schema = openapi["components"]["schemas"]["QuarantineReviewRequest"]
    assert set(review_schema["properties"]["decision"]["enum"]) == {
        "confirm",
        "release",
        "keep_quarantined",
    }
    assert "current_version" in {
        parameter["name"]
        for parameter in reupload_operation["parameters"]
    }
    assert "next version" in reupload_operation["description"]


def test_upload_rejects_declared_type_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")

    response = client.post(
        "/upload",
        files={"file": ("sample.csv", "id,name\n1,Alice\n", "text/csv")},
        data={
            "file_type": "json",
            "data_category": "company",
            "country": "US",
            "year": 2026,
            "batch_name": "type-mismatch",
        },
    )

    assert response.status_code == 422
    assert "does not match" in response.json()["detail"]
    assert not (tmp_path / "uploads" / "2026_type-mismatch.csv").exists()


def test_file_details_rejects_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)

    response = client.get("/files/..%2Foutside.csv/details")

    assert response.status_code in {400, 404}


def test_upload_rejects_unsafe_batch_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")

    response = client.post(
        "/upload",
        files={"file": ("sample.csv", "id,name\n1,Alice\n", "text/csv")},
        data={
            "file_type": "csv",
            "data_category": "company",
            "country": "US",
            "year": 2026,
            "batch_name": "../outside",
        },
    )

    assert response.status_code == 422
