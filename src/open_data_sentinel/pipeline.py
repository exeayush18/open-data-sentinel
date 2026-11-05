from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from .config import SourceConfig
from .quality import data_fingerprint, evaluate_quality, infer_schema, schema_fingerprint
from .sources import connector_for
from .storage import DatasetSnapshot, PipelineRun, QualityCheck, previous_schema

logger = logging.getLogger(__name__)


def run_source(session: Session, source: SourceConfig) -> PipelineRun:
    run = PipelineRun(source_name=source.name)
    session.add(run)
    session.commit()

    try:
        extraction = connector_for(source).extract(source)
        schema = infer_schema(extraction.records)
        prior_schema = previous_schema(session, source.name)
        checks = evaluate_quality(
            extraction.records,
            source.primary_key,
            prior_schema,
            min_records=source.min_records,
            max_null_rate=source.max_null_rate,
        )

        run.record_count = len(extraction.records)
        run.status = "success"
        run.finished_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(
            DatasetSnapshot(
                run_id=run.id,
                schema_json=schema,
                schema_fingerprint=schema_fingerprint(schema),
                data_fingerprint=data_fingerprint(extraction.records),
                metadata_json=extraction.metadata,
            )
        )
        session.add_all(
            QualityCheck(
                run_id=run.id,
                name=check.name,
                status=check.status,
                observed_json=check.observed,
                threshold_json=check.threshold,
            )
            for check in checks
        )
        session.commit()
        logger.info("Completed source=%s records=%s", source.name, run.record_count)
    except Exception as error:
        session.rollback()
        run.status = "failed"
        run.error = str(error)
        run.finished_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(run)
        session.commit()
        logger.exception("Failed source=%s", source.name)
    return run
