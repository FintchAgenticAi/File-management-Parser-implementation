from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, UploadFile


class ProcessingManagerClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def process_csv(self, filename: str, supplier_name: str, country: str) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            "/processing/jobs",
            json={"csv_filename": filename, "supplier_name": supplier_name, "country": country},
        )

    async def download_quarantine_export(self, data_batch_id: int) -> httpx.Response:
        return await self._request(
            "GET",
            f"/processing/batches/{data_batch_id}/quarantine-export",
        )

    async def review_quarantine(self, quarantine_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            f"/processing/quarantine/{quarantine_id}/review",
            json=payload,
        )

    async def reupload_csv(
        self,
        data_batch_id: int,
        file: UploadFile,
        next_version: int,
    ) -> dict[str, Any]:
        content = await file.read()
        return await self._request_json(
            "POST",
            f"/processing/batches/{data_batch_id}/reupload",
            files={"file": (file.filename or "reviewed.csv", content, "text/csv")},
            data={"version": str(next_version)},
        )

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Processing Manager returned invalid JSON.") from exc

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Data Processing Manager is unavailable.") from exc
        if response.status_code >= 400:
            detail = response.text or "Data Processing Manager request failed."
            raise HTTPException(status_code=response.status_code, detail=detail)
        return response
