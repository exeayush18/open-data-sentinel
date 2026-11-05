import pytest

from open_data_sentinel.sources import (
    catalog_record,
    coerce_records,
    follow_path,
    parse_first_table,
)


def test_parse_first_table_returns_records():
    html = """
    <table>
      <tr><th>city</th><th>count</th></tr>
      <tr><td>Delhi</td><td>2</td></tr>
      <tr><td>Mumbai</td><td>3</td></tr>
    </table>
    """

    assert parse_first_table(html) == [
        {"city": "Delhi", "count": "2"},
        {"city": "Mumbai", "count": "3"},
    ]


def test_json_helpers_handle_nested_payloads_and_scalars():
    assert follow_path({"result": {"items": [1]}}, "result.items") == [1]
    assert coerce_records([1, {"id": 2}], "sample") == [{"value": 1}, {"id": 2}]

    with pytest.raises(ValueError, match="data_path"):
        follow_path({"result": {}}, "result.items")


def test_catalog_record_preserves_dataset_identity_and_resource_count():
    dataset = {
        "id": "dataset-1",
        "name": "city-data",
        "title": "City data",
        "resources": [{"id": "resource-1"}, {"id": "resource-2"}],
    }

    assert catalog_record(dataset) == {
        "id": "dataset-1",
        "name": "city-data",
        "title": "City data",
        "metadata_created": None,
        "metadata_modified": None,
        "resource_count": 2,
    }
