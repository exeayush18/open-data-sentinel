from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn
from sqlalchemy.orm import Session

from .api import create_app
from .config import load_config
from .pipeline import run_source
from .storage import initialize_database, make_engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Open Data Sentinel")
    commands = parser.add_subparsers(dest="command", required=True)

    init_db = commands.add_parser("init-db", help="Create database tables")
    init_db.add_argument("--config", default="examples/sources.yml")

    run = commands.add_parser("run", help="Ingest and validate configured sources")
    run.add_argument("--config", default="examples/sources.yml")
    run.add_argument("--source", help="Run one source by name")

    serve = commands.add_parser("serve", help="Start the health API")
    serve.add_argument("--database-url")
    serve.add_argument("--config", default="examples/sources.yml")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.command == "serve":
        config = load_config(Path(args.config))
        database_url = args.database_url or config.database_url
        freshness_policy = {source.name: source.stale_after_hours for source in config.sources}
        uvicorn.run(create_app(database_url, freshness_policy), host=args.host, port=args.port)
        return

    config = load_config(Path(args.config))
    initialize_database(config.database_url)
    if args.command == "init-db":
        print("Database initialized")
        return

    selected_sources = [source for source in config.sources if args.source in {None, source.name}]
    if args.source and not selected_sources:
        raise SystemExit(f"No source named '{args.source}' in {args.config}")

    engine = make_engine(config.database_url)
    with Session(engine) as session:
        for source in selected_sources:
            result = run_source(session, source)
            print(f"{result.source_name}: {result.status} ({result.record_count} records)")


if __name__ == "__main__":
    main()
