from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .storage import PipelineRun, QualityCheck, make_engine


def create_app(
    database_url: str | None = None, stale_after_hours: dict[str, int] | None = None
) -> FastAPI:
    engine = make_engine(database_url or os.getenv("DATABASE_URL", "sqlite:///./sentinel.db"))
    stale_after_hours = stale_after_hours or {}
    app = FastAPI(title="Open Data Sentinel", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}

    @app.get("/datasets")
    def datasets() -> list[dict[str, object]]:
        with Session(engine) as session:
            runs = session.scalars(
                select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(100)
            ).all()
        latest_by_source: dict[str, PipelineRun] = {}
        for run in runs:
            latest_by_source.setdefault(run.source_name, run)
        return [serialize_run(run, stale_after_hours) for run in latest_by_source.values()]

    @app.get("/datasets/{source_name}")
    def dataset(source_name: str) -> dict[str, object]:
        with Session(engine) as session:
            run = session.scalar(
                select(PipelineRun)
                .where(PipelineRun.source_name == source_name)
                .order_by(PipelineRun.started_at.desc())
            )
        if run is None:
            raise HTTPException(status_code=404, detail="Source not found")
        return serialize_run(run, stale_after_hours)

    @app.get("/datasets/{source_name}/history")
    def history(source_name: str, limit: int = 20) -> list[dict[str, object]]:
        if not 1 <= limit <= 100:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
        with Session(engine) as session:
            runs = session.scalars(
                select(PipelineRun)
                .where(PipelineRun.source_name == source_name)
                .order_by(PipelineRun.started_at.desc())
                .limit(limit)
            ).all()
        if not runs:
            raise HTTPException(status_code=404, detail="Source not found")
        return [serialize_run(run, stale_after_hours) for run in runs]

    @app.get("/datasets/{source_name}/checks")
    def checks(source_name: str, limit: int = 100) -> list[dict[str, object]]:
        if not 1 <= limit <= 500:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
        with Session(engine) as session:
            source_exists = session.scalar(
                select(PipelineRun.id).where(PipelineRun.source_name == source_name).limit(1)
            )
            if source_exists is None:
                raise HTTPException(status_code=404, detail="Source not found")
            results = session.scalars(
                select(QualityCheck)
                .join(PipelineRun)
                .where(PipelineRun.source_name == source_name)
                .order_by(QualityCheck.id.desc())
                .limit(limit)
            ).all()
        return [serialize_check(check) for check in results]

    return app


def serialize_run(
    run: PipelineRun, stale_after_hours: dict[str, int] | None = None
) -> dict[str, object]:
    threshold = (stale_after_hours or {}).get(run.source_name)
    is_stale = None
    if run.status == "success" and run.finished_at and threshold is not None:
        elapsed = datetime.now(UTC).replace(tzinfo=None) - run.finished_at
        age_hours = elapsed.total_seconds() / 3600
        is_stale = age_hours > threshold

    return {
        "source_name": run.source_name,
        "status": run.status,
        "record_count": run.record_count,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "error": run.error,
        "is_stale": is_stale,
    }


def serialize_check(check: QualityCheck) -> dict[str, object]:
    return {
        "name": check.name,
        "status": check.status,
        "observed": check.observed_json,
        "threshold": check.threshold_json,
    }


app = create_app()
