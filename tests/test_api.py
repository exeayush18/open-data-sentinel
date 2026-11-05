from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from open_data_sentinel.api import create_app
from open_data_sentinel.storage import PipelineRun, QualityCheck, initialize_database, make_engine


@pytest.mark.anyio
async def test_api_exposes_latest_run_history_and_quality_checks(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'sentinel.db'}"
    initialize_database(database_url)
    engine = make_engine(database_url)

    with Session(engine) as session:
        run = PipelineRun(
            source_name="city-service-requests",
            status="success",
            record_count=100,
            started_at=datetime.now(UTC).replace(tzinfo=None),
            finished_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(run)
        session.flush()
        session.add(
            QualityCheck(
                run_id=run.id,
                name="row_count",
                status="pass",
                observed_json={"rows": 100},
                threshold_json={"minimum": 50},
            )
        )
        session.commit()

    transport = httpx.ASGITransport(
        app=create_app(database_url, {"city-service-requests": 24})
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        latest = await client.get("/datasets/city-service-requests")
        history = await client.get("/datasets/city-service-requests/history")
        checks = await client.get("/datasets/city-service-requests/checks")

    assert latest.status_code == 200
    assert latest.json()["is_stale"] is False
    assert history.json()[0]["record_count"] == 100
    assert checks.json() == [
        {
            "name": "row_count",
            "status": "pass",
            "observed": {"rows": 100},
            "threshold": {"minimum": 50},
        }
    ]
