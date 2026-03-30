# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import sqlite3


def init_db(db_path: str) -> None:
    """Create the file_cache table if it does not exist."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_cache (
                path TEXT PRIMARY KEY,
                mtime REAL NOT NULL,
                record_count INTEGER,
                schema_name TEXT
            )
            """
        )
        conn.commit()


def get_cached(db_path: str, path: str, mtime: float) -> tuple[int, str] | None:
    """
    Return (record_count, schema_name) if a row exists for `path` with a
    matching `mtime`, otherwise None.
    """
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT record_count, schema_name FROM file_cache WHERE path = ? AND mtime = ?",
            (path, mtime),
        ).fetchone()
    if row is None:
        return None
    return (row[0], row[1])


def set_cached(
    db_path: str,
    path: str,
    mtime: float,
    record_count: int,
    schema_name: str,
) -> None:
    """Insert or replace a row in the cache."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO file_cache (path, mtime, record_count, schema_name)
            VALUES (?, ?, ?, ?)
            """,
            (path, mtime, record_count, schema_name),
        )
        conn.commit()
