from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QualityResult:
    name: str
    status: str
    observed: dict[str, Any]
    threshold: dict[str, Any]


def infer_schema(records: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    schema: dict[str, set[str]] = {}
    for record in records:
        for key, value in record.items():
            schema.setdefault(key, set()).add(type_name(value))
    return {key: sorted(types) for key, types in sorted(schema.items())}


def schema_fingerprint(schema: dict[str, list[str]]) -> str:
    payload = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def data_fingerprint(records: Iterable[dict[str, Any]]) -> str:
    normalized = [json.dumps(record, sort_keys=True, default=str) for record in records]
    payload = "\n".join(sorted(normalized))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def detect_schema_drift(
    previous: dict[str, list[str]] | None, current: dict[str, list[str]]
) -> dict[str, list[str]]:
    if previous is None:
        return {"added": [], "removed": [], "type_changed": []}

    previous_columns = set(previous)
    current_columns = set(current)
    return {
        "added": sorted(current_columns - previous_columns),
        "removed": sorted(previous_columns - current_columns),
        "type_changed": sorted(
            key for key in previous_columns & current_columns if previous[key] != current[key]
        ),
    }


def evaluate_quality(
    records: list[dict[str, Any]],
    primary_key: str | None,
    previous_schema: dict[str, list[str]] | None,
    min_records: int = 1,
    max_null_rate: float = 0.8,
) -> list[QualityResult]:
    checks = [
        QualityResult(
            name="row_count",
            status="pass" if len(records) >= min_records else "warn",
            observed={"rows": len(records)},
            threshold={"minimum": min_records},
        )
    ]

    if primary_key:
        values = [
            field_value(record, primary_key)
            for record in records
            if field_value(record, primary_key) is not None
        ]
        duplicate_count = len(values) - len(set(map(str, values)))
        checks.append(
            QualityResult(
                name="duplicate_primary_key",
                status="fail" if duplicate_count else "pass",
                observed={"primary_key": primary_key, "duplicates": duplicate_count},
                threshold={"duplicates": 0},
            )
        )

    if records:
        for column in infer_schema(records):
            null_count = sum(record.get(column) is None for record in records)
            null_rate = null_count / len(records)
            checks.append(
                QualityResult(
                    name=f"null_rate:{column}",
                    status="warn" if null_rate > max_null_rate else "pass",
                    observed={"column": column, "null_rate": null_rate},
                    threshold={"maximum": max_null_rate},
                )
            )

    current_schema = infer_schema(records)
    drift = detect_schema_drift(previous_schema, current_schema)
    has_drift = any(drift.values())
    checks.append(
        QualityResult(
            name="schema_drift",
            status="warn" if has_drift else "pass",
            observed=drift,
            threshold={"allowed_changes": 0},
        )
    )
    return checks


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (dict, list)):
        return "json"
    return "string"


def field_value(record: dict[str, Any], field: str) -> Any:
    value: Any = record
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value
