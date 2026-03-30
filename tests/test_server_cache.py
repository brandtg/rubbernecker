# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import os
import sqlite3
import tempfile

from rubbernecker.server.cache import get_cached, init_db, set_cached


def test_init_db_creates_table():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "db.sqlite")
        init_db(db_path)
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='file_cache'"
            ).fetchall()
            assert len(rows) == 1
            # Check columns
            cols = conn.execute("PRAGMA table_info(file_cache)").fetchall()
            col_names = {row[1] for row in cols}
            assert col_names == {"path", "mtime", "record_count", "schema_name"}


def test_get_cached_miss_empty_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "db.sqlite")
        init_db(db_path)
        result = get_cached(db_path, "/a.avro", 1.0)
        assert result is None


def test_set_and_get_cached_hit():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "db.sqlite")
        init_db(db_path)
        set_cached(db_path, "/a.avro", 1.0, 42, "Page")
        result = get_cached(db_path, "/a.avro", 1.0)
        assert result == (42, "Page")


def test_get_cached_miss_stale_mtime():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "db.sqlite")
        init_db(db_path)
        set_cached(db_path, "/a.avro", 1.0, 42, "Page")
        result = get_cached(db_path, "/a.avro", 2.0)
        assert result is None


def test_set_cached_overwrites_existing():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "db.sqlite")
        init_db(db_path)
        set_cached(db_path, "/a.avro", 1.0, 42, "Page")
        set_cached(db_path, "/a.avro", 2.0, 99, "StandardPage")
        # Old mtime miss
        assert get_cached(db_path, "/a.avro", 1.0) is None
        # New mtime hit
        result = get_cached(db_path, "/a.avro", 2.0)
        assert result == (99, "StandardPage")
