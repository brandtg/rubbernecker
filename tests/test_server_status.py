# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile

from avrokit import avro_writer, parse_url

from rubbernecker.crawl.tool import SCHEMA as PAGE_SCHEMA
from rubbernecker.server.app import create_app
from rubbernecker.server.status import get_status_result
from rubbernecker.sitemap.tool import ENTRY_SCHEMA


def _write_pages_avro(path: str, records: list[dict]) -> None:
    url = parse_url(path).with_mode("wb")
    with avro_writer(url, PAGE_SCHEMA) as w:
        for rec in records:
            w.append(rec)


def _make_page(url: str, ts: int = 1000) -> dict:
    return {"url": url, "timestamp": ts, "body": None, "error": None, "metadata": None}


def _make_error_page(url: str, ts: int = 1000) -> dict:
    return {
        "url": url,
        "timestamp": ts,
        "body": None,
        "error": "timeout",
        "metadata": None,
    }


def test_get_status_result_text_input():
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "urls.txt")
        output_path = os.path.join(tmpdir, "pages.avro")
        urls = [f"https://example.com/{i}" for i in range(5)]
        with open(input_path, "w") as f:
            f.write("\n".join(urls) + "\n")
        _write_pages_avro(
            output_path, [_make_page(u, 1000 + i) for i, u in enumerate(urls[:3])]
        )
        result = get_status_result(input_path, output_path)
        assert result is not None
        assert result.count_input == 5
        assert result.count_processed == 3


def test_get_status_result_jsonl_input():
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "urls.jsonl")
        output_path = os.path.join(tmpdir, "pages.avro")
        urls = [f"https://example.com/{i}" for i in range(5)]
        with open(input_path, "w") as f:
            for u in urls:
                f.write(json.dumps({"url": u}) + "\n")
        _write_pages_avro(
            output_path, [_make_page(u, 1000 + i) for i, u in enumerate(urls[:3])]
        )
        result = get_status_result(input_path, output_path)
        assert result is not None
        assert result.count_input == 5
        assert result.count_processed == 3


def test_get_status_result_avro_input():
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "urls.avro")
        output_path = os.path.join(tmpdir, "pages.avro")
        entries = [
            {
                "url": f"https://example.com/{i}",
                "lastmod": None,
                "changefreq": None,
                "priority": None,
            }
            for i in range(5)
        ]
        url = parse_url(input_path).with_mode("wb")
        with avro_writer(url, ENTRY_SCHEMA) as w:
            for e in entries:
                w.append(e)
        _write_pages_avro(
            output_path,
            [_make_page(str(entries[j]["url"]), 1000 + j) for j in range(3)],
        )
        result = get_status_result(input_path, output_path)
        assert result is not None
        assert result.count_input == 5
        assert result.count_processed == 3


def test_get_status_result_returns_none_on_corrupt_output():
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "urls.txt")
        output_path = os.path.join(tmpdir, "pages.avro")
        with open(input_path, "w") as f:
            f.write("https://example.com\n")
        # Write garbage bytes
        with open(output_path, "wb") as f:
            f.write(b"\x00\x01\x02garbage bytes not valid avro")
        # Should not raise
        result = get_status_result(input_path, output_path)
        # The StatusTool catches errors internally, but the input count should work
        # An unreadable output is handled gracefully (returns result with 0 processed)
        assert result is not None  # input count still works
        assert result.count_processed == 0


def test_directory_detail_route_crawl_dataset():
    with tempfile.TemporaryDirectory() as tmpdir:
        sub = os.path.join(tmpdir, "crawl1")
        os.makedirs(sub)
        pages_path = os.path.join(sub, "pages.avro")
        urls_path = os.path.join(sub, "urls.txt")
        _write_pages_avro(pages_path, [_make_page("https://example.com", 1000)])
        with open(urls_path, "w") as f:
            f.write("https://example.com\nhttps://example.com/b\n")
        app = create_app(root=tmpdir)
        with app.test_client() as client:
            resp = client.get("/dir/crawl1")
            assert resp.status_code == 200
            body = resp.data.decode("utf-8")
            # Should show processed count or total
            assert "crawl1" in body


def test_directory_detail_route_404():
    with tempfile.TemporaryDirectory() as tmpdir:
        app = create_app(root=tmpdir)
        with app.test_client() as client:
            resp = client.get("/dir/nonexistent")
            assert resp.status_code == 404


def test_directory_detail_route_degraded_no_urls_companion():
    """pages.avro exists but no urls.* companion — should show degraded record count view."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sub = os.path.join(tmpdir, "crawl_nourls")
        os.makedirs(sub)
        pages_path = os.path.join(sub, "pages.avro")
        _write_pages_avro(
            pages_path,
            [_make_page(f"https://example.com/{i}", 1000 + i) for i in range(4)],
        )
        app = create_app(root=tmpdir)
        with app.test_client() as client:
            resp = client.get("/dir/crawl_nourls")
            assert resp.status_code == 200
            body = resp.data.decode("utf-8")
            assert "Crawl Status" in body
            assert "No input URL file found" in body
            assert "4" in body  # record count visible
