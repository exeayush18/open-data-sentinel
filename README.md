# Open Data Sentinel

Open Data Sentinel is a lightweight data-observability pipeline for public datasets. It extracts data from public APIs or permitted HTML tables, records reproducible snapshots, detects schema drift, and stores quality results for review.

The project is intentionally designed as a portfolio-grade data engineering system rather than a one-off script:

- Connector abstraction for JSON, Socrata, CKAN catalog metadata, and permitted HTML tables
- Incremental run history in PostgreSQL or SQLite for local development
- Schema and data fingerprints for reproducibility
- Per-source policies for minimum record counts, null-rate limits, timeouts, retry budgets, and freshness windows
- Checks for low-volume extracts, duplicate keys, high null rates, and schema changes
- FastAPI endpoints for source health, run history, and quality-check history
- Docker Compose deployment with PostgreSQL
- GitHub Actions CI for tests and linting

## Architecture

```text
source configuration
        |
        v
connector -> normalized records -> schema/data fingerprints
        |                                  |
        +--------> quality checks <--------+
                         |
                         v
              PostgreSQL / SQLite run history
                         |
                         v
                 FastAPI health endpoints
```

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,postgres]'
ods init-db --config examples/sources.yml
ods run --config examples/sources.yml --source city-service-requests
ods serve
```

Open `http://127.0.0.1:8000/docs` to inspect the API. After a pipeline run, use:

- `/datasets` for the latest source status
- `/datasets/{source_name}` for a source's latest run and freshness state
- `/datasets/{source_name}/history` for recent runs
- `/datasets/{source_name}/checks` for persisted quality checks

The JSON and HTML-table connector types are templates: point them only at datasets and pages you are
authorized to access. The bundled Socrata, CKAN, and USGS examples use public endpoints and can be run directly.

The included CKAN example monitors the public UK National Data Library metadata API and does not download
underlying dataset files.

## Run with Docker

```bash
docker compose up --build
```

The API runs at `http://localhost:8000`. To run ingestion in the container, use a second terminal:

```bash
docker compose exec sentinel ods run --config examples/sources.yml --source city-service-requests
```

## Configure a source

```yaml
sources:
  - name: city-service-requests
    kind: socrata
    url: https://data.cityofnewyork.us/resource/erm2-nwe9.json
    primary_key: unique_key
    max_records: 1000
    min_records: 500
    max_null_rate: 0.85
    stale_after_hours: 30
    timeout_seconds: 20
    max_retries: 3
```

Supported `kind` values:

- `socrata`: JSON resource endpoint; the pipeline applies a `$limit` parameter.
- `json`: JSON list or object. Use `data_path` for a nested list.
- `ckan`: CKAN `package_show` or `package_search` endpoint; the pipeline monitors metadata,
  not underlying data files.
- `html_table`: first table from a public page that permits extraction.

## Quality semantics

| Check | Status behavior |
| --- | --- |
| Row count | Warns when an extract is below its configured `min_records`. |
| Duplicate primary key | Fails when configured non-null keys repeat. |
| Null rate | Warns when a field exceeds its configured `max_null_rate`. |
| Schema drift | Warns when columns are added, removed, or change inferred types. |

Nested JSON fields, such as `sourceInfo.siteCode`, can be used as primary keys.

The check thresholds are deliberately visible and source-specific. Future work can add scheduled runs,
alert webhooks, and a dashboard.

## Test

```bash
pytest
ruff check .
```

## Boundaries

Open Data Sentinel is built for public, authorized, and terms-compliant sources. It does not include automation to circumvent authentication, paywalls, rate limits, or access controls.

## License

MIT
