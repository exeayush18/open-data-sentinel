from datetime import UTC, datetime, timedelta

from open_data_sentinel.api import serialize_run
from open_data_sentinel.quality import (
    data_fingerprint,
    detect_schema_drift,
    evaluate_quality,
    infer_schema,
    schema_fingerprint,
)
from open_data_sentinel.storage import PipelineRun


def test_schema_is_stable_and_fingerprinted_deterministically():
    first = [{"id": 1, "name": "Ada"}, {"id": 2, "name": None}]
    second = [{"name": None, "id": 2}, {"name": "Ada", "id": 1}]

    schema = infer_schema(first)

    assert schema == {"id": ["integer"], "name": ["null", "string"]}
    assert schema_fingerprint(schema) == schema_fingerprint(infer_schema(second))
    assert data_fingerprint(first) == data_fingerprint(second)


def test_quality_detects_duplicate_keys_nulls_and_schema_drift():
    records = [{"id": "a", "value": None}, {"id": "a", "value": None}]
    previous_schema = {"id": ["string"], "old_column": ["string"]}

    results = {result.name: result for result in evaluate_quality(records, "id", previous_schema)}

    assert results["duplicate_primary_key"].status == "fail"
    assert results["null_rate:value"].status == "warn"
    assert results["schema_drift"].status == "warn"
    assert results["schema_drift"].observed == {
        "added": ["value"],
        "removed": ["old_column"],
        "type_changed": [],
    }


def test_quality_supports_nested_primary_keys():
    records = [{"source": {"id": "a"}}, {"source": {"id": "a"}}]

    results = {result.name: result for result in evaluate_quality(records, "source.id", None)}

    assert results["duplicate_primary_key"].status == "fail"


def test_schema_drift_is_empty_for_matching_schemas():
    schema = {"id": ["integer"], "name": ["string"]}

    assert detect_schema_drift(schema, schema) == {"added": [], "removed": [], "type_changed": []}


def test_dataset_health_marks_old_successful_run_as_stale():
    run = PipelineRun(
        source_name="catalog",
        status="success",
        started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=30),
        finished_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=29),
    )

    assert serialize_run(run, {"catalog": 24})["is_stale"] is True
