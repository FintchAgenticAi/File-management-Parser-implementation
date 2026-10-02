from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app import routes

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
    assert second_payload["message"] == "uploaded this file before"
    assert second_payload["output_file"] == first_payload["output_file"]


def test_upload_csv_skips_conversion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(routes, "_get_converter", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("converter should not run for CSV input")))

    csv_content = "id,name,amount\n1,Alice,100\n2,Bob,200\n3,Charlie,300\n"
    response = client.post(
        "/upload",
        files={"file": ("sample.csv", csv_content, "text/csv")},
        data={
            "file_type": "csv",
            "data_category": "company",
            "country": "US",
            "year": 2026,
            "batch_name": "batch-csv",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "file already csv, saved directly"
    assert payload["output_file"] == "2026_batch-csv.csv"
    assert "sub_file_type" not in payload
    assert payload["file_type"] == "csv"

    upload_path = tmp_path / "uploads" / "2026_batch-csv.csv"
    assert upload_path.exists()

    stored_csv = tmp_path / "2026_batch-csv.csv"
    assert stored_csv.exists()
    assert stored_csv.read_text(encoding="utf-8-sig") == csv_content


def test_send_csv_to_processing_manager_returns_metadata_and_rows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(routes.upload_service, "upload_dir", tmp_path / "uploads")

    csv_content = "id,name,amount\n1,Alice,100\n2,Bob,200\n"
    upload_response = client.post(
        "/upload",
        files={"file": ("sample.csv", csv_content, "text/csv")},
        data={
            "file_type": "csv",
            "data_category": "company",
            "country": "US",
            "year": 2026,
            "batch_name": "batch-csv",
        },
    )

    assert upload_response.status_code == 200
    response = client.post("/files/2026_batch-csv.csv/send-to-processing-manager")

    assert response.status_code == 200
    payload = response.json()
    assert payload["event"] == "csv_ready_for_processing"
    assert payload["csv_file"]["filename"] == "2026_batch-csv.csv"
    assert payload["csv_file"]["file_hash"] == upload_response.json()["file_hash"]
    assert payload["csv_file"]["data_category"] == "company"
    assert payload["included_details"] == {
        "columns": ["id", "name", "amount"],
        "row_count": 2,
        "rows": [
            {"id": "1", "name": "Alice", "amount": "100"},
            {"id": "2", "name": "Bob", "amount": "200"},
        ],
    }


def test_upload_openapi_exposes_single_file_type_enum() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]["Body_upload_file_upload_post"]
    properties = schema["properties"]

    assert "file_type" in properties
    assert "input_file_type" not in properties
    assert "sub_file_type" not in properties
    assert response.json()["components"]["schemas"]["FileType"]["enum"] == ["json", "xml", "csv", "xlsx", "pdf", "jpg", "jpeg", "png", "gif", "webp"]
    assert response.json()["paths"]["/upload"]["post"]["tags"] == ["File Manager"]

    parameters = response.json()["paths"]["/upload"]["post"]["parameters"]
    assert any(param["name"] == "version" and param["in"] == "query" for param in parameters)


def test_quarantine_notification_contains_downloadable_export_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "EXTRACT_DIR", tmp_path)
    (tmp_path / "2026_batch-csv.csv").write_text("id,name\n1,Alice\n", encoding="utf-8")
    (tmp_path / "2026_batch-csv.meta.json").write_text(
        '{"filename":"2026_batch-csv.csv","original_filename":"sample.csv",'
        '"processor":"file_manager","file_hash":"hash","file_type":"csv",'
        '"data_category":"company","country":"US","year":2026,'
        '"batch_name":"batch-csv","csv_path":"2026_batch-csv.csv"}',
        encoding="utf-8",
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
        "message": "Quarantine records require review.",
        "data_batch_id": 42,
        "filename": "xport-quarantine.csv",
        "download_url": "/processing/batches/42/quarantine-export",
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
