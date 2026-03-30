# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile
from unittest.mock import patch

from avrokit import avro_writer, parse_url

from rubbernecker.crawl.tool import SCHEMA as PAGE_SCHEMA
from rubbernecker.server.discovery import discover_directories, find_avro_files


def _write_page_avro(path: str, records: list[dict]) -> None:
    url = parse_url(path).with_mode("wb")
    with avro_writer(url, PAGE_SCHEMA) as w:
        for rec in records:
            w.append(rec)


def _make_page(url: str = "https://example.com") -> dict:
    return {
        "url": url,
        "timestamp": 1000,
        "body": None,
        "error": None,
        "metadata": None,
    }


def test_find_avro_files_empty_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = find_avro_files(tmpdir)
        assert result == []


def test_find_avro_files_single_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "output.avro")
        _write_page_avro(path, [_make_page()])
        result = find_avro_files(tmpdir)
        assert len(result) == 1
        assert result[0].path == path
        assert result[0].mtime > 0
        assert result[0].record_count is None


def test_find_avro_files_nested():
    with tempfile.TemporaryDirectory() as tmpdir:
        sub1 = os.path.join(tmpdir, "a")
        sub2 = os.path.join(tmpdir, "b", "c")
        os.makedirs(sub1)
        os.makedirs(sub2)
        p1 = os.path.join(sub1, "x.avro")
        p2 = os.path.join(sub2, "y.avro")
        _write_page_avro(p1, [_make_page()])
        _write_page_avro(p2, [_make_page()])
        result = find_avro_files(tmpdir)
        paths = {r.path for r in result}
        assert p1 in paths
        assert p2 in paths


def test_find_avro_files_ignores_non_avro():
    with tempfile.TemporaryDirectory() as tmpdir:
        avro_path = os.path.join(tmpdir, "output.avro")
        txt_path = os.path.join(tmpdir, "urls.txt")
        json_path = os.path.join(tmpdir, "output.json")
        _write_page_avro(avro_path, [_make_page()])
        with open(txt_path, "w") as f:
            f.write("https://example.com\n")
        with open(json_path, "w") as f:
            f.write("{}\n")
        result = find_avro_files(tmpdir)
        assert len(result) == 1
        assert result[0].path == avro_path


def test_discover_directories_crawl_dataset_detection():
    with tempfile.TemporaryDirectory() as tmpdir:
        sub = os.path.join(tmpdir, "crawl1")
        os.makedirs(sub)
        pages_path = os.path.join(sub, "pages.avro")
        urls_path = os.path.join(sub, "urls.txt")
        _write_page_avro(pages_path, [_make_page()])
        with open(urls_path, "w") as f:
            f.write("https://example.com\n")
        db_path = os.path.join(tmpdir, "db.sqlite")
        dirs = discover_directories(tmpdir, db_path)
        assert len(dirs) == 1
        d = dirs[0]
        assert d.is_crawl_dataset is True
        assert d.input_url_path == urls_path


def test_discover_directories_not_crawl_without_urls():
    with tempfile.TemporaryDirectory() as tmpdir:
        sub = os.path.join(tmpdir, "crawl1")
        os.makedirs(sub)
        pages_path = os.path.join(sub, "pages.avro")
        _write_page_avro(pages_path, [_make_page()])
        db_path = os.path.join(tmpdir, "db.sqlite")
        dirs = discover_directories(tmpdir, db_path)
        assert len(dirs) == 1
        assert dirs[0].is_crawl_dataset is False


def test_discover_directories_populates_record_count_from_avro():
    with tempfile.TemporaryDirectory() as tmpdir:
        sub = os.path.join(tmpdir, "ds")
        os.makedirs(sub)
        avro_path = os.path.join(sub, "data.avro")
        _write_page_avro(
            avro_path,
            [
                _make_page("https://a.com"),
                _make_page("https://b.com"),
                _make_page("https://c.com"),
            ],
        )
        db_path = os.path.join(tmpdir, "db.sqlite")
        dirs = discover_directories(tmpdir, db_path)
        assert len(dirs) == 1
        file_info = dirs[0].files[0]
        assert file_info.record_count == 3


def test_discover_directories_uses_cache_on_second_call():
    with tempfile.TemporaryDirectory() as tmpdir:
        sub = os.path.join(tmpdir, "ds")
        os.makedirs(sub)
        avro_path = os.path.join(sub, "data.avro")
        _write_page_avro(avro_path, [_make_page()])
        db_path = os.path.join(tmpdir, "db.sqlite")
        # First call — populates cache
        discover_directories(tmpdir, db_path)
        # Second call — should hit cache, not call CountTool again
        with patch("rubbernecker.server.discovery.CountTool") as mock_ct:
            discover_directories(tmpdir, db_path)
            mock_ct.assert_not_called()
