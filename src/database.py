"""Chinook in-memory SQLite setup + a safe query helper.

The engine/db creation is the cell provided by the brief (Task 1). On top of it
we expose `run_query`, which always uses *parameterized* SQL (decision: grill
#11) so user-supplied artist/genre/song strings can never be SQL-injected.
"""

import sqlite3

import requests
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

CHINOOK_URL = (
    "https://raw.githubusercontent.com/lerocha/chinook-database/master/"
    "ChinookDatabase/DataSources/Chinook_Sqlite.sql"
)


def get_engine_for_chinook_db():
    """Pull the SQL file, populate an in-memory database, and create an engine."""
    response = requests.get(CHINOOK_URL)
    response.raise_for_status()
    sql_script = response.text

    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.executescript(sql_script)

    return create_engine(
        "sqlite://",
        creator=lambda: connection,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


engine = get_engine_for_chinook_db()


def run_query(sql: str, params: dict | None = None) -> list[dict]:
    """Run a parameterized SELECT and return rows as dicts.

    Always pass user values via `params` (e.g. {"p": "%rolling stones%"}),
    never by f-string interpolation into `sql`.
    """
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        return [dict(row._mapping) for row in result]
