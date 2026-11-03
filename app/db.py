"""Engine/session setup and a tiny SQL-file migration runner."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def utcnow() -> datetime:
    """Naive UTC timestamps everywhere (portable across SQLite and Postgres)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_engine(url: str) -> Engine:
    kwargs: dict = {}
    is_sqlite = url.startswith("sqlite")
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        else:
            m = re.match(r"sqlite:///(.+)", url)
            if m:
                Path(m.group(1)).parent.mkdir(parents=True, exist_ok=True)
    else:
        kwargs["pool_pre_ping"] = True
    engine = create_engine(url, **kwargs)
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def run_migrations(engine: Engine, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every unapplied migrations/*.sql in filename order. Returns versions applied."""
    applied_now: list[str] = []
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version VARCHAR(100) PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
        )
        done = {r[0] for r in conn.exec_driver_sql("SELECT version FROM schema_migrations")}
        for path in sorted(directory.glob("*.sql")):
            if path.stem in done:
                continue
            for stmt in path.read_text().split(";"):
                if stmt.strip():
                    conn.exec_driver_sql(stmt)
            conn.execute(
                text("INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :t)"),
                {"v": path.stem, "t": utcnow()},
            )
            applied_now.append(path.stem)
    return applied_now
