from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(255), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshots: Mapped[list[DatasetSnapshot]] = relationship(back_populates="run")
    checks: Mapped[list[QualityCheck]] = relationship(back_populates="run")


class DatasetSnapshot(Base):
    __tablename__ = "dataset_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    schema_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    data_fingerprint: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    run: Mapped[PipelineRun] = relationship(back_populates="snapshots")


class QualityCheck(Base):
    __tablename__ = "quality_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20))
    observed_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    threshold_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    run: Mapped[PipelineRun] = relationship(back_populates="checks")


def make_engine(database_url: str):
    return create_engine(database_url, future=True)


def initialize_database(database_url: str) -> None:
    Base.metadata.create_all(make_engine(database_url))


def previous_schema(session: Session, source_name: str) -> dict[str, list[str]] | None:
    statement = (
        select(DatasetSnapshot.schema_json)
        .join(PipelineRun)
        .where(PipelineRun.source_name == source_name, PipelineRun.status == "success")
        .order_by(DatasetSnapshot.created_at.desc())
        .limit(1)
    )
    return session.scalar(statement)


def latest_runs(session: Session) -> list[PipelineRun]:
    statement = select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(100)
    return list(session.scalars(statement))
