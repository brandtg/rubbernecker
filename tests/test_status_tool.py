# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile

import pytest
from avrokit import avro_writer, parse_url

from rubbernecker.crawl.tool import SCHEMA as PAGE_SCHEMA
from rubbernecker.crawl.tool import InputFormat
from rubbernecker.status.tool import DEFAULT_WINDOW, StatusTool, StatusToolResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_page_avro(path: str, records: list[dict]) -> None:
    """Write a list of Page records to an Avro file at `path`."""
    url = parse_url(path).with_mode("wb")
    with avro_writer(url, PAGE_SCHEMA) as writer:
        for rec in records:
            writer.append(rec)


def write_text_urls(path: str, urls: list[str]) -> None:
    with open(path, "w") as f:
        f.write("\n".join(urls) + "\n")


def write_json_urls(path: str, urls: list[str]) -> None:
    with open(path, "w") as f:
        for u in urls:
            f.write(json.dumps({"url": u}) + "\n")


# ---------------------------------------------------------------------------
# StatusToolResult unit tests
# ---------------------------------------------------------------------------


class TestStatusToolResult:
    def test_defaults(self):
        r = StatusToolResult()
        assert r.count_input == 0
        assert r.count_processed == 0
        assert r.count_success == 0
        assert r.count_error == 0
        assert r.count_remaining == 0
        assert r.error_rate is None
        assert r.overall_rate is None
        assert r.recent_rate is None
        assert r.eta_overall == "N/A"
        assert r.eta_recent == "N/A"

    def test_count_remaining(self):
        r = StatusToolResult(count_input=100, count_processed=30)
        assert r.count_remaining == 70

    def test_count_remaining_never_negative(self):
        # processed > input can happen if input count drifts
        r = StatusToolResult(count_input=10, count_processed=20)
        assert r.count_remaining == 0

    def test_error_rate_zero_processed(self):
        r = StatusToolResult(count_processed=0, count_error=0)
        assert r.error_rate is None

    def test_error_rate(self):
        r = StatusToolResult(count_processed=100, count_error=10)
        assert r.error_rate == pytest.approx(0.1)

    def test_overall_rate_requires_two_records(self):
        r = StatusToolResult(
            count_processed=1,
            first_timestamp=1000,
            last_timestamp=1010,
        )
        assert r.overall_rate is None

    def test_overall_rate_requires_time_delta(self):
        r = StatusToolResult(
            count_processed=50,
            first_timestamp=1000,
            last_timestamp=1000,  # same second
        )
        assert r.overall_rate is None

    def test_overall_rate(self):
        # 100 records over 200 seconds → 0.5 pages/sec
        r = StatusToolResult(
            count_processed=100,
            first_timestamp=1000,
            last_timestamp=1200,
        )
        assert r.overall_rate == pytest.approx(0.5)

    def test_recent_rate_requires_two_timestamps(self):
        r = StatusToolResult(window_timestamps=[1000])
        assert r.recent_rate is None

    def test_recent_rate_requires_time_delta(self):
        r = StatusToolResult(window_timestamps=[1000, 1000, 1000])
        assert r.recent_rate is None

    def test_recent_rate(self):
        # 9 intervals over 10 seconds → (10-1)/10 = 0.9 pages/sec
        # window_timestamps has 10 entries spanning 10 seconds
        r = StatusToolResult(
            window_timestamps=list(range(1000, 1010))  # 10 timestamps
        )
        # 9 intervals / (1009 - 1000) = 9/9 = 1.0 pages/sec
        assert r.recent_rate == pytest.approx(1.0)

    def test_eta_overall(self):
        # 50 remaining at 0.5 pages/sec → 100 seconds
        r = StatusToolResult(
            count_input=150,
            count_processed=100,
            first_timestamp=1000,
            last_timestamp=1200,
        )
        assert r.eta_overall == "0:01:40"

    def test_eta_overall_zero_remaining(self):
        r = StatusToolResult(
            count_input=100,
            count_processed=100,
            first_timestamp=1000,
            last_timestamp=1200,
        )
        assert r.eta_overall == "N/A"

    def test_to_text_contains_key_fields(self):
        r = StatusToolResult(
            count_input=1000,
            count_processed=500,
            count_success=490,
            count_error=10,
            first_timestamp=1000000,
            last_timestamp=1001000,
        )
        text = r.to_text(
            input_urls=["urls.txt"],
            output_urls=["output.avro"],
            window=100,
        )
        assert "1,000" in text
        assert "500" in text
        assert "490" in text
        assert "10" in text
        assert "Overall rate" in text
        assert "Recent rate" in text
        assert "ETA (overall)" in text
        assert "ETA (recent)" in text

    def test_to_text_shows_duplicates(self):
        r = StatusToolResult(
            count_input=100,
            count_input_duplicates=5,
        )
        text = r.to_text(
            input_urls=["urls.txt"],
            output_urls=["output.avro"],
            window=100,
        )
        assert "Duplicates" in text
        assert "bloom filter" in text

    def test_to_text_no_duplicates_line_when_zero(self):
        r = StatusToolResult(count_input=100, count_input_duplicates=0)
        text = r.to_text(
            input_urls=["urls.txt"],
            output_urls=["output.avro"],
            window=100,
        )
        assert "Duplicates" not in text

    def test_to_json_dict_keys(self):
        r = StatusToolResult(
            count_input=100,
            count_processed=50,
            count_success=45,
            count_error=5,
        )
        d = r.to_json_dict(
            input_urls=["urls.txt"],
            output_urls=["output.avro"],
            window=100,
        )
        assert "input" in d
        assert "output" in d
        assert "remaining" in d
        assert "timing" in d
        assert "rates" in d
        assert "eta" in d
        assert d["output"]["processed"] == 50
        assert d["output"]["success"] == 45
        assert d["output"]["errors"] == 5
        assert d["remaining"] == 50


# ---------------------------------------------------------------------------
# StatusTool.count_input tests
# ---------------------------------------------------------------------------


class TestStatusToolCountInput:
    def test_text_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            write_text_urls(path, ["https://example.com/a", "https://example.com/b"])
            tool = StatusTool()
            urls = [parse_url(path)]
            total, dups = tool.count_input(urls, InputFormat.TEXT)
            assert total == 2
            assert dups == 0

    def test_text_format_with_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            write_text_urls(
                path,
                [
                    "https://example.com/a",
                    "https://example.com/b",
                    "https://example.com/a",
                ],
            )
            tool = StatusTool()
            urls = [parse_url(path)]
            total, dups = tool.count_input(urls, InputFormat.TEXT)
            assert total == 3
            assert dups == 1

    def test_json_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.jsonl")
            write_json_urls(path, ["https://example.com/a", "https://example.com/b"])
            tool = StatusTool()
            urls = [parse_url(path)]
            total, dups = tool.count_input(urls, InputFormat.JSON)
            assert total == 2
            assert dups == 0

    def test_json_format_with_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.jsonl")
            write_json_urls(
                path,
                [
                    "https://example.com/a",
                    "https://example.com/a",
                    "https://example.com/b",
                ],
            )
            tool = StatusTool()
            urls = [parse_url(path)]
            total, dups = tool.count_input(urls, InputFormat.JSON)
            assert total == 3
            assert dups == 1

    def test_avro_format(self):
        from avrokit import avro_schema

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.avro")
            schema = avro_schema(
                {
                    "name": "UrlRecord",
                    "type": "record",
                    "fields": [{"name": "url", "type": "string"}],
                }
            )
            with avro_writer(parse_url(path).with_mode("wb"), schema) as w:
                w.append({"url": "https://example.com/a"})
                w.append({"url": "https://example.com/b"})
                w.append({"url": "https://example.com/c"})
            tool = StatusTool()
            urls = [parse_url(path)]
            total, dups = tool.count_input(urls, InputFormat.AVRO)
            assert total == 3
            assert dups == 0  # avro fast-count skips dup detection

    def test_multiple_text_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = os.path.join(tmpdir, "a.txt")
            p2 = os.path.join(tmpdir, "b.txt")
            write_text_urls(p1, ["https://example.com/a"])
            write_text_urls(p2, ["https://example.com/b", "https://example.com/c"])
            tool = StatusTool()
            urls = [parse_url(p1), parse_url(p2)]
            total, dups = tool.count_input(urls, InputFormat.TEXT)
            assert total == 3
            assert dups == 0

    def test_multiple_text_files_cross_file_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = os.path.join(tmpdir, "a.txt")
            p2 = os.path.join(tmpdir, "b.txt")
            write_text_urls(p1, ["https://example.com/a"])
            write_text_urls(p2, ["https://example.com/a"])  # same URL
            tool = StatusTool()
            urls = [parse_url(p1), parse_url(p2)]
            total, dups = tool.count_input(urls, InputFormat.TEXT)
            assert total == 2
            assert dups == 1


# ---------------------------------------------------------------------------
# StatusTool.scan_output tests
# ---------------------------------------------------------------------------


class TestStatusToolScanOutput:
    def test_empty_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "output.avro")
            write_page_avro(path, [])
            tool = StatusTool()
            result = tool.scan_output([parse_url(path)])
            assert result.count_processed == 0
            assert result.count_success == 0
            assert result.count_error == 0
            assert result.first_timestamp is None
            assert result.last_timestamp is None

    def test_nonexistent_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "does_not_exist.avro")
            tool = StatusTool()
            result = tool.scan_output([parse_url(path)])
            assert result.count_processed == 0

    def test_success_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "output.avro")
            write_page_avro(
                path,
                [
                    {"url": "https://a.com", "timestamp": 1000, "body": "<html/>"},
                    {"url": "https://b.com", "timestamp": 1010, "body": "<html/>"},
                    {"url": "https://c.com", "timestamp": 1020, "body": "<html/>"},
                ],
            )
            tool = StatusTool()
            result = tool.scan_output([parse_url(path)])
            assert result.count_processed == 3
            assert result.count_success == 3
            assert result.count_error == 0
            assert result.first_timestamp == 1000
            assert result.last_timestamp == 1020

    def test_error_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "output.avro")
            write_page_avro(
                path,
                [
                    {"url": "https://a.com", "timestamp": 1000, "body": "<html/>"},
                    {"url": "https://b.com", "timestamp": 1010, "error": "timeout"},
                    {"url": "https://c.com", "timestamp": 1020, "error": "404"},
                ],
            )
            tool = StatusTool()
            result = tool.scan_output([parse_url(path)])
            assert result.count_processed == 3
            assert result.count_success == 1
            assert result.count_error == 2

    def test_window_timestamps_capped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "output.avro")
            records = [
                {"url": f"https://example.com/{i}", "timestamp": 1000 + i, "body": "x"}
                for i in range(200)
            ]
            write_page_avro(path, records)
            tool = StatusTool()
            result = tool.scan_output([parse_url(path)], window=50)
            # Window should contain only the last 50 timestamps
            assert len(result.window_timestamps) == 50
            assert result.window_timestamps[-1] == 1000 + 199
            assert result.window_timestamps[0] == 1000 + 150

    def test_multiple_output_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = os.path.join(tmpdir, "out1.avro")
            p2 = os.path.join(tmpdir, "out2.avro")
            write_page_avro(
                p1,
                [
                    {"url": "https://a.com", "timestamp": 1000, "body": "<html/>"},
                    {"url": "https://b.com", "timestamp": 1010, "error": "err"},
                ],
            )
            write_page_avro(
                p2,
                [
                    {"url": "https://c.com", "timestamp": 1020, "body": "<html/>"},
                ],
            )
            tool = StatusTool()
            result = tool.scan_output([parse_url(p1), parse_url(p2)])
            assert result.count_processed == 3
            assert result.count_success == 2
            assert result.count_error == 1
            assert result.first_timestamp == 1000
            assert result.last_timestamp == 1020


# ---------------------------------------------------------------------------
# StatusTool.status integration tests
# ---------------------------------------------------------------------------


class TestStatusToolStatus:
    def test_full_flow_text_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "urls.txt")
            output_path = os.path.join(tmpdir, "output.avro")
            write_text_urls(
                input_path,
                [f"https://example.com/{i}" for i in range(10)],
            )
            write_page_avro(
                output_path,
                [
                    {
                        "url": f"https://example.com/{i}",
                        "timestamp": 1000 + i * 5,
                        "body": "<html/>",
                    }
                    for i in range(6)
                ],
            )
            tool = StatusTool()
            result = tool.status(
                input_url_strs=[input_path],
                output_url_strs=[output_path],
                input_format=InputFormat.TEXT,
                window=DEFAULT_WINDOW,
            )
            assert result.count_input == 10
            assert result.count_processed == 6
            assert result.count_success == 6
            assert result.count_error == 0
            assert result.count_remaining == 4
            assert result.count_input_duplicates == 0

    def test_full_flow_with_errors_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "urls.txt")
            output_path = os.path.join(tmpdir, "output.avro")
            urls = [f"https://example.com/{i}" for i in range(5)]
            urls.append(urls[0])  # one duplicate
            write_text_urls(input_path, urls)
            write_page_avro(
                output_path,
                [
                    {"url": "https://example.com/0", "timestamp": 2000, "body": "x"},
                    {"url": "https://example.com/1", "timestamp": 2010, "error": "err"},
                    {"url": "https://example.com/2", "timestamp": 2020, "body": "x"},
                ],
            )
            tool = StatusTool()
            result = tool.status(
                input_url_strs=[input_path],
                output_url_strs=[output_path],
            )
            assert result.count_input == 6
            assert result.count_input_duplicates == 1
            assert result.count_processed == 3
            assert result.count_success == 2
            assert result.count_error == 1
            assert result.error_rate == pytest.approx(1 / 3)

    def test_output_not_started(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "urls.txt")
            write_text_urls(input_path, ["https://example.com/a"])
            tool = StatusTool()
            result = tool.status(
                input_url_strs=[input_path],
                output_url_strs=[os.path.join(tmpdir, "nonexistent.avro")],
            )
            assert result.count_input == 1
            assert result.count_processed == 0
            assert result.count_remaining == 1

    def test_text_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "urls.txt")
            output_path = os.path.join(tmpdir, "output.avro")
            write_text_urls(input_path, [f"https://example.com/{i}" for i in range(5)])
            write_page_avro(
                output_path,
                [
                    {
                        "url": f"https://example.com/{i}",
                        "timestamp": 1000 + i * 3,
                        "body": "x",
                    }
                    for i in range(3)
                ],
            )
            tool = StatusTool()
            result = tool.status(
                input_url_strs=[input_path],
                output_url_strs=[output_path],
            )
            text = result.to_text(
                input_urls=[input_path],
                output_urls=[output_path],
                window=DEFAULT_WINDOW,
            )
            assert "Crawl Status" in text
            assert "Progress" in text
            assert "Timing" in text

    def test_json_output_is_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "urls.txt")
            output_path = os.path.join(tmpdir, "output.avro")
            write_text_urls(input_path, ["https://example.com/a"])
            write_page_avro(
                output_path,
                [{"url": "https://example.com/a", "timestamp": 9999, "body": "x"}],
            )
            tool = StatusTool()
            result = tool.status(
                input_url_strs=[input_path],
                output_url_strs=[output_path],
            )
            d = result.to_json_dict(
                input_urls=[input_path],
                output_urls=[output_path],
                window=DEFAULT_WINDOW,
            )
            # Must be round-trip serialisable
            serialised = json.dumps(d)
            parsed = json.loads(serialised)
            assert parsed["output"]["processed"] == 1
