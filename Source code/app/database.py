from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import mysql.connector
from mysql.connector import Error

from app.config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER , EXTRACT_DIR


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

def _connect():
    try:
        print(MYSQL_HOST , MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER,MYSQL_PASSWORD)


        return mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
        )
    except Error as exc:
        raise DatabaseError("Could not connect to the shared Data Processing database.") from exc


def ensure_supplier_and_batch(
    supplier_name: str, batch_name: str, country: str, version: int, data_category: str, year: int, file_hash : str
    ) -> DataBatchRecord:
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        print(f"Ensuring supplier '{data_category}' and batch '{year}' exist in the database.")
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
            SELECT data_batch_id, supplier_id, batch_name, country, created_at, version, data_category, `year`
            FROM data_batch
            WHERE supplier_id = %s AND batch_name = %s AND country = %s AND version = %s AND data_category = %s AND `year` = %s AND file_hash = %s
            LIMIT 1
            """,
            (supplier_id, batch_name, country, version, data_category, year , file_hash),
        )
        batch = cursor.fetchone()
        if batch is None:
            cursor.execute(
                """
                INSERT INTO data_batch (supplier_id, batch_name, country, created_at, version, data_category, `year`, file_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s ,%s)
                """,
                (supplier_id, batch_name, country, datetime.now(), version, data_category, year, file_hash),
            )
            print(supplier_id, batch_name, country, datetime.now(), version, data_category, year, file_hash)
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
            )
        
        return _record_from_row(batch)
    except Error as exc:
        connection.rollback()
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
        cursor.execute(
            """
            SELECT data_batch_id, supplier_id, batch_name, country, created_at, version, data_category, `year`
            FROM data_batch
            WHERE batch_name = %s AND version = %s
            ORDER BY data_batch_id DESC LIMIT 1
            """,
            (batch_name, version),
        )
        row = cursor.fetchone()
        return _record_from_row(row) if row else None
    except Error as exc:
        raise DatabaseError("Could not read the shared Data Processing database.") from exc
    finally:
        cursor.close()
        connection.close()
        
        
def find_existing_csv_details_by_hash(file_hash: str, base_dir: Path = EXTRACT_DIR) -> CSVFileDetails | None:
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT *
            FROM data_batch
            WHERE file_hash = %s
            LIMIT 1
            """,
            (file_hash,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return  DataBatchRecord(
                data_batch_id=int(row["data_batch_id"]),
                supplier_id=int(row["supplier_id"]),
                batch_name=str(row["batch_name"]),
                country=str(row["country"]),
                created_at=row["created_at"],
                version=int(row["version"]),
                data_category=str(row["data_category"]),
                year=int(row["year"]),
            )
    except Error as exc:
        print(exc)
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
    )
