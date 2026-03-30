# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile

from avrokit import avro_writer, parse_url

from rubbernecker.crawl.tool import SCHEMA as PAGE_SCHEMA
from rubbernecker.server.app import create_app
from rubbernecker.server.reader import get_records_page, get_schema_json


def _write_page_avro(path: str, records: list[dict]) -> None:
    url = parse_url(path).with_mode("wb")
    with avro_writer(url, PAGE_SCHEMA) as w:
        for rec in records:
            w.append(rec)


def _make_page(url: str = "https://example.com", ts: int = 1000) -> dict:
    return {"url": url, "timestamp": ts, "body": None, "error": None, "metadata": None}


def test_get_schema_json_returns_valid_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "data.avro")
        _write_page_avro(path, [_make_page()])
        result = get_schema_json(path)
        assert result is not None
        parsed = json.loads(result)
        assert parsed.get("name") == "Page"


def test_get_schema_json_returns_none_on_corrupt_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "corrupt.avro")
        with open(path, "wb") as f:
            f.write(b"\x00garbage")
        result = get_schema_json(path)
        assert result is None


def test_get_records_page_first_page():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "data.avro")
        _write_page_avro(
            path, [_make_page(f"https://example.com/{i}") for i in range(10)]
        )
        records, has_more = get_records_page(path, offset=0, limit=5)
        assert len(records) == 5
        assert has_more is True


def test_get_records_page_last_page():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "data.avro")
        _write_page_avro(
            path, [_make_page(f"https://example.com/{i}") for i in range(10)]
        )
        records, has_more = get_records_page(path, offset=8, limit=5)
        assert len(records) == 2
        assert has_more is False


def test_get_records_page_exact_boundary():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "data.avro")
        _write_page_avro(
            path, [_make_page(f"https://example.com/{i}") for i in range(10)]
        )
        records, has_more = get_records_page(path, offset=5, limit=5)
        assert len(records) == 5
        assert has_more is False


def test_get_records_page_beyond_end():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "data.avro")
        _write_page_avro(
            path, [_make_page(f"https://example.com/{i}") for i in range(10)]
        )
        records, has_more = get_records_page(path, offset=20, limit=5)
        assert records == []
        assert has_more is False


def test_file_detail_route_200():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "data.avro")
        _write_page_avro(path, [_make_page()])
        app = create_app(root=tmpdir)
        with app.test_client() as client:
            resp = client.get("/file/data.avro")
            assert resp.status_code == 200
            body = resp.data.decode("utf-8")
            assert "Page" in body


def test_file_detail_route_404_nonexistent():
    with tempfile.TemporaryDirectory() as tmpdir:
        app = create_app(root=tmpdir)
        with app.test_client() as client:
            resp = client.get("/file/no/such/file.avro")
            assert resp.status_code == 404


def test_file_detail_route_404_non_avro():
    with tempfile.TemporaryDirectory() as tmpdir:
        urls_path = os.path.join(tmpdir, "urls.txt")
        with open(urls_path, "w") as f:
            f.write("https://example.com\n")
        app = create_app(root=tmpdir)
        with app.test_client() as client:
            resp = client.get("/file/urls.txt")
            assert resp.status_code == 404
