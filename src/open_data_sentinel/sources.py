from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .config import SourceConfig


@dataclass(frozen=True)
class Extraction:
    records: list[dict[str, Any]]
    metadata: dict[str, Any]


class SourceConnector:
    def extract(self, source: SourceConfig) -> Extraction:
        raise NotImplementedError


class JsonConnector(SourceConnector):
    def extract(self, source: SourceConfig) -> Extraction:
        params = {"$limit": source.max_records} if source.kind == "socrata" else None
        payload = fetch_json(source, params=params)
        value = follow_path(payload, source.data_path) if source.data_path else payload
        records = coerce_records(value, source.name)
        return Extraction(records=records[: source.max_records], metadata={"url": source.url})


class CkanConnector(SourceConnector):
    def extract(self, source: SourceConfig) -> Extraction:
        payload = fetch_json(source)
        result = payload.get("result", {})
        if "resources" in result:
            records = [dict(resource) for resource in result["resources"]]
        else:
            records = [catalog_record(dataset) for dataset in result.get("results", [])]
        return Extraction(
            records=records[: source.max_records],
            metadata={"url": source.url, "dataset_title": result.get("title")},
        )


class HtmlTableConnector(SourceConnector):
    def extract(self, source: SourceConfig) -> Extraction:
        response = fetch_response(source)
        return Extraction(
            records=parse_first_table(response.text)[: source.max_records],
            metadata={"url": source.url, "content_type": response.headers.get("content-type")},
        )


def connector_for(source: SourceConfig) -> SourceConnector:
    if source.kind in {"json", "socrata"}:
        return JsonConnector()
    if source.kind == "ckan":
        return CkanConnector()
    if source.kind == "html_table":
        return HtmlTableConnector()
    raise ValueError(f"Unsupported source kind: {source.kind}")


def fetch_json(source: SourceConfig, params: dict[str, Any] | None = None) -> Any:
    return fetch_response(source, params=params).json()


def fetch_response(source: SourceConfig, params: dict[str, Any] | None = None) -> httpx.Response:
    retryable_statuses = {429, 500, 502, 503, 504}
    with httpx.Client(timeout=source.timeout_seconds, follow_redirects=True) as client:
        for attempt in range(1, source.max_retries + 1):
            try:
                response = client.get(
                    source.url,
                    params=params,
                    headers={"User-Agent": "OpenDataSentinel/0.1 (+https://github.com/)"},
                )
                if response.status_code in retryable_statuses and attempt < source.max_retries:
                    time.sleep(0.25 * (2 ** (attempt - 1)))
                    continue
                response.raise_for_status()
                return response
            except (httpx.ConnectError, httpx.ReadTimeout):
                if attempt == source.max_retries:
                    raise
                time.sleep(0.25 * (2 ** (attempt - 1)))

    raise RuntimeError("HTTP retry loop ended unexpectedly.")


def coerce_records(value: Any, source_name: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [record if isinstance(record, dict) else {"value": record} for record in value]
    if isinstance(value, dict):
        return [value]
    raise ValueError(f"Source '{source_name}' returned an unsupported JSON shape.")


def catalog_record(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": dataset.get("id"),
        "name": dataset.get("name"),
        "title": dataset.get("title"),
        "metadata_created": dataset.get("metadata_created"),
        "metadata_modified": dataset.get("metadata_modified"),
        "resource_count": len(dataset.get("resources", [])),
    }


def follow_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"Could not resolve data_path '{path}'.")
        current = current[part]
    return current


def parse_first_table(html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("No HTML table found.")

    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [cell.get_text(" ", strip=True) for cell in rows[0].find_all(["th", "td"])]
    if not headers:
        raise ValueError("The first table has no headers.")

    records = []
    for row in rows[1:]:
        cells = [cell.get_text(" ", strip=True) or None for cell in row.find_all(["td", "th"])]
        if cells:
            records.append(dict(zip(headers, cells, strict=False)))
    return records
