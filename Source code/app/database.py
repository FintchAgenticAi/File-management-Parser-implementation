from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import mysql.connector
from mysql.connector import Error

from app.config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER, EXTRACT_DIR


logger = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    """Raised when the shared Data Processing database cannot be used."""


@dataclass(frozen=True)
class DataBatchRecord:
    data_batch_id: int
    supplier_id: int
    batch_name: str
    country: str
    created_at: datetime | None
    version: int
    data_category: str
    year: int
    file_hash: str | None = None
    file_type: str | None = None
    original_filename: str | None = None


def _connect():
    try:
        return mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            connection_timeout=10,
        )
    except Error as exc:
        logger.error(
            "Database connection failed (host=%s port=%s database=%s user=%s): %s",
            MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER, exc,
        )
        raise DatabaseError("Could not connect to the shared Data Processing database.") from exc


def check_connection() -> None:
    """Open a connection and run a trivial query; raises DatabaseError on failure."""
    connection = _connect()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
    except Error as exc:
        raise DatabaseError("Connected, but the database did not answer a test query.") from exc
    finally:
        connection.close()


def _ensure_file_type_column(cursor) -> None:
    cursor.execute("SHOW COLUMNS FROM data_batch LIKE 'file_type'")
    if cursor.fetchone() is not None:
        return
    try:
        cursor.execute("ALTER TABLE data_batch ADD COLUMN file_type VARCHAR(16) NULL")
    except Error as exc:
        if exc.errno != 1060:
            raise


def _ensure_original_filename_column(cursor) -> None:
    cursor.execute("SHOW COLUMNS FROM data_batch LIKE 'original_filename'")
    if cursor.fetchone() is not None:
        return
    try:
        cursor.execute("ALTER TABLE data_batch ADD COLUMN original_filename VARCHAR(255) NULL")
    except Error as exc:
        if exc.errno != 1060:
            raise


def _ensure_output_filename_column(cursor) -> None:
    cursor.execute("SHOW COLUMNS FROM data_batch LIKE 'output_filename'")
    if cursor.fetchone() is not None:
        return
    cursor.execute("SHOW COLUMNS FROM data_batch LIKE 'csv_filename'")
    has_legacy_column = cursor.fetchone() is not None
    try:
        if has_legacy_column:
            cursor.execute("ALTER TABLE data_batch CHANGE COLUMN csv_filename output_filename VARCHAR(255) NULL")
        else:
            cursor.execute("ALTER TABLE data_batch ADD COLUMN output_filename VARCHAR(255) NULL")
    except Error as exc:
        if exc.errno not in (1060, 1054):
            raise


def _ensure_columns(cursor) -> None:
    _ensure_file_type_column(cursor)
    _ensure_original_filename_column(cursor)
    _ensure_output_filename_column(cursor)


def ensure_schema() -> None:
    """Add the optional data_batch columns; called once at application startup."""
    connection = _connect()
    try:
        cursor = connection.cursor()
        _ensure_columns(cursor)
        connection.commit()
    except Error as exc:
        raise DatabaseError("Could not add the file_type/original_filename columns to data_batch.") from exc
    finally:
        connection.close()


def ensure_supplier_and_batch(
    supplier_name: str,
    batch_name: str,
    country: str,
    version: int,
    data_category: str,
    year: int,
    file_hash: str | None,
    file_type: str = "csv",
    original_filename: str | None = None,
    output_filename: str | None = None,
) -> DataBatchRecord:
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        _ensure_columns(cursor)
        cursor.execute(
            "SELECT supplier_id FROM supplier WHERE supplier_name = %s LIMIT 1",
            (supplier_name,),
        )
        supplier = cursor.fetchone()
        if supplier is None:
            cursor.execute("INSERT INTO supplier (supplier_name) VALUES (%s)", (supplier_name,))
            supplier_id = int(cursor.lastrowid)
        else:
            supplier_id = int(supplier["supplier_id"])

        cursor.execute(
            """
            SELECT data_batch_id, supplier_id, batch_name, country, created_at, version, data_category,             `year`, file_hash, file_type, original_filename
            FROM data_batch
            WHERE supplier_id = %s AND batch_name = %s AND country = %s AND version = %s AND data_category = %s AND `year` = %s AND file_hash <=> %s AND file_type = %s
            LIMIT 1
            """,
            (supplier_id, batch_name, country, version, data_category, year, file_hash, file_type),
        )
        batch = cursor.fetchone()
        if batch is None:
            cursor.execute(
                """
                INSERT INTO data_batch (supplier_id, batch_name, country, created_at, version, data_category,                                 `year`, file_hash, file_type, original_filename, output_filename)
                                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                                (
                                    supplier_id, batch_name, country, datetime.now(), version, data_category, year,
                                                    file_hash, file_type, original_filename, output_filename,
                                ),
                            )
            connection.commit()
            return DataBatchRecord(
                data_batch_id=int(cursor.lastrowid),
                supplier_id=supplier_id,
                batch_name=batch_name,
                country=country,
                created_at=None,
                version=version,
                data_category=data_category,
                year=year,
                file_hash=file_hash,
                file_type=file_type,
                original_filename=original_filename,
            )

        return _record_from_row(batch)
    except Error as exc:
        connection.rollback()
        logger.error("Database error saving supplier/batch: %s", exc)
        raise DatabaseError("Could not save the supplier or data batch.") from exc
    finally:
        cursor.close()
        connection.close()


def get_batch_for_file(filename: str) -> DataBatchRecord | None:
    stem = filename.rsplit(".", 1)[0]
    parts = stem.split("_")
    if len(parts) < 2 or not parts[0].isdigit():
        return None
    if parts[-1].lower().startswith("v") and parts[-1][1:].isdigit():
        version = int(parts[-1][1:])
        batch_name = "_".join(parts[1:-1])
    else:
        version = 1
        batch_name = "_".join(parts[1:])
    if not batch_name:
        return None

    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        _ensure_columns(cursor)
        cursor.execute(
            """
            SELECT data_batch_id, supplier_id, batch_name, country, created_at, version, data_category, `year`, file_hash, file_type, original_filename
            FROM data_batch
            WHERE `year` = %s AND batch_name = %s AND version = %s
            ORDER BY data_batch_id DESC LIMIT 1
            """,
            (int(parts[0]), batch_name, version),
        )
        row = cursor.fetchone()
        return _record_from_row(row) if row else None
    except Error as exc:
        raise DatabaseError("Could not read the shared Data Processing database.") from exc
    finally:
        cursor.close()
        connection.close()


def find_batch_by_output_name(year: int, batch_name: str, version: int) -> DataBatchRecord | None:
    """Return the batch that already owns the CSV name year_batch_vN, if any."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        _ensure_columns(cursor)
        cursor.execute(
            """
            SELECT data_batch_id, supplier_id, batch_name, country, created_at, version, data_category, `year`, file_hash, file_type, original_filename
            FROM data_batch
            WHERE `year` = %s AND batch_name = %s AND version = %s
            ORDER BY data_batch_id DESC LIMIT 1
            """,
            (year, batch_name, version),
        )
        row = cursor.fetchone()
        return _record_from_row(row) if row else None
    except Error as exc:
        raise DatabaseError("Could not read the shared Data Processing database.") from exc
    finally:
        cursor.close()
        connection.close()


def find_existing_csv_details_by_hash(
    file_hash: str,
    base_dir: Path = EXTRACT_DIR,
) -> DataBatchRecord | None:
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        _ensure_columns(cursor)
        cursor.execute(
            """
            SELECT data_batch_id, supplier_id, batch_name, country, created_at, version, data_category, `year`, file_hash, file_type, original_filename
            FROM data_batch
            WHERE file_hash = %s
            LIMIT 1
            """,
            (file_hash,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return _record_from_row(row)
    except Error as exc:
        raise DatabaseError("Could not read the shared Data Processing database.") from exc
    finally:
        cursor.close()
        connection.close()


def _record_from_row(row: dict[str, object]) -> DataBatchRecord:
    return DataBatchRecord(
        data_batch_id=int(row["data_batch_id"]),
        supplier_id=int(row["supplier_id"]),
        batch_name=str(row["batch_name"]),
        country=str(row["country"]),
        created_at=row["created_at"],
        version=int(row["version"]),
        data_category=str(row["data_category"]),
        year=int(row["year"]),
        file_hash=str(row["file_hash"]) if row.get("file_hash") is not None else None,
        file_type=str(row["file_type"]) if row.get("file_type") is not None else None,
        original_filename=str(row["original_filename"]) if row.get("original_filename") is not None else None,
    )
