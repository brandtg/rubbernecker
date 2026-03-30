# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile
from unittest.mock import patch

from avrokit import avro_writer, parse_url

from rubbernecker.crawl.tool import SCHEMA as PAGE_SCHEMA
from rubbernecker.server.discovery import discover_directories
from rubbernecker.server.models import AvroFileInfo
from rubbernecker.server.pipeline import compute_deltas, order_pipeline_stages


def _write_page_avro(path: str, records: list[dict]) -> None:
    url = parse_url(path).with_mode("wb")
    with avro_writer(url, PAGE_SCHEMA) as w:
        for rec in records:
            w.append(rec)


def _make_page(url: str = "https://example.com", ts: int = 1000) -> dict:
    return {"url": url, "timestamp": ts, "body": None, "error": None, "metadata": None}


def _make_file(
    path: str, mtime: float, count: int | None, name: str | None = None
) -> AvroFileInfo:
    return AvroFileInfo(
        path=path,
        rel_path=os.path.basename(path),
        mtime=mtime,
        record_count=count,
        schema_name=name,
    )


def test_order_pipeline_stages_by_mtime():
    f1 = _make_file("/dir/a.avro", 3.0, 10)
    f2 = _make_file("/dir/b.avro", 1.0, 20)
    f3 = _make_file("/dir/c.avro", 2.0, 30)
    result = order_pipeline_stages([f1, f2, f3])
    assert [f.mtime for f in result] == [1.0, 2.0, 3.0]


def test_order_pipeline_stages_alpha_tiebreak():
    f1 = _make_file("/dir/b.avro", 1.0, 10)
    f2 = _make_file("/dir/a.avro", 1.0, 20)
    result = order_pipeline_stages([f1, f2])
    # Both have same mtime — sort alphabetically by path
    assert result[0].path == "/dir/a.avro"
    assert result[1].path == "/dir/b.avro"


def test_compute_deltas_first_element_is_none():
    files = [
        _make_file("/dir/a.avro", 1.0, 100),
        _make_file("/dir/b.avro", 2.0, 90),
        _make_file("/dir/c.avro", 3.0, 45),
    ]
    deltas = compute_deltas(files)
    assert deltas == [None, -10, -45]


def test_compute_deltas_with_none_record_count():
    files = [
        _make_file("/dir/a.avro", 1.0, 100),
        _make_file("/dir/b.avro", 2.0, None),
        _make_file("/dir/c.avro", 3.0, 45),
    ]
    deltas = compute_deltas(files)
    assert deltas[0] is None
    assert deltas[1] is None  # adjacent to None
    assert deltas[2] is None  # b has None record_count


def test_schema_name_populated_in_discovery():
    with tempfile.TemporaryDirectory() as tmpdir:
        sub = os.path.join(tmpdir, "ds")
        os.makedirs(sub)
        avro_path = os.path.join(sub, "data.avro")
        _write_page_avro(avro_path, [_make_page()])
        db_path = os.path.join(tmpdir, "db.sqlite")
        dirs = discover_directories(tmpdir, db_path)
        assert len(dirs) == 1
        file_info = dirs[0].files[0]
        assert file_info.schema_name == "Page"


def test_schema_name_cached():
    with tempfile.TemporaryDirectory() as tmpdir:
        sub = os.path.join(tmpdir, "ds")
        os.makedirs(sub)
        avro_path = os.path.join(sub, "data.avro")
        _write_page_avro(avro_path, [_make_page()])
        db_path = os.path.join(tmpdir, "db.sqlite")
        # First call populates the cache
        discover_directories(tmpdir, db_path)
        # Second call should read from cache — avro_reader should not be called
        with patch("rubbernecker.server.discovery.avro_reader") as mock_reader:
            discover_directories(tmpdir, db_path)
            mock_reader.assert_not_called()
