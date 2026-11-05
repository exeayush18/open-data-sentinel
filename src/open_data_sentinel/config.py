from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

SourceKind = Literal["json", "socrata", "ckan", "html_table"]


@dataclass(frozen=True)
class SourceConfig:
    name: str
    kind: SourceKind
    url: str
    primary_key: str | None = None
    max_records: int = 1_000
    min_records: int = 1
    max_null_rate: float = 0.8
    stale_after_hours: int = 24
    data_path: str | None = None
    timeout_seconds: float = 20.0
    max_retries: int = 3

    def __post_init__(self) -> None:
        if self.max_records < 1:
            raise ValueError(f"Source '{self.name}' must set max_records to at least 1.")
        if self.min_records < 0:
            raise ValueError(f"Source '{self.name}' cannot set a negative min_records.")
        if not 0 <= self.max_null_rate <= 1:
            raise ValueError(f"Source '{self.name}' max_null_rate must be between 0 and 1.")
        if self.timeout_seconds <= 0 or self.max_retries < 1:
            raise ValueError(f"Source '{self.name}' has an invalid timeout or retry policy.")


@dataclass(frozen=True)
class AppConfig:
    database_url: str
    sources: list[SourceConfig]


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file) or {}

    if not isinstance(raw.get("sources"), list):
        raise ValueError("Configuration requires a 'sources' list.")

    sources = [SourceConfig(**source) for source in raw["sources"]]
    names = [source.name for source in sources]
    if len(set(names)) != len(names):
        raise ValueError("Source names must be unique.")

    return AppConfig(
        database_url=raw.get("database_url", "sqlite:///./sentinel.db"),
        sources=sources,
    )
