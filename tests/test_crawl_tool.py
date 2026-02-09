# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile

import pytest
from avrokit import avro_reader, avro_schema, avro_writer, parse_url

from rubbernecker.crawl.bloomfilter import BloomFilter
from rubbernecker.crawl.tool import CrawlTool, InputFormat


class TestCrawlToolBloomFilterKey:
    def test_simple_url(self):
        tool = CrawlTool()
        key = tool.bloom_filter_key("https://example.com/page")
        assert key == "example.com:/page:"

    def test_url_with_query(self):
        tool = CrawlTool()
        key = tool.bloom_filter_key("https://example.com/page?foo=bar")
        assert key == "example.com:/page:foo=bar"

    def test_url_normalization_lowercase(self):
        tool = CrawlTool()
        key = tool.bloom_filter_key("https://EXAMPLE.COM/PAGE")
        assert "example.com" in key
        assert "/PAGE" not in key
        assert "/page" in key

    def test_url_without_path(self):
        tool = CrawlTool()
        key = tool.bloom_filter_key("https://example.com")
        assert key == "example.com::"

    def test_url_with_port(self):
        tool = CrawlTool()
        key = tool.bloom_filter_key("https://example.com:8080/page")
        assert key == "example.com:8080:/page:"


class TestCrawlToolLoadBloomFilter:
    def test_load_empty_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_url = parse_url(os.path.join(tmpdir, "output.avro"))
            tool = CrawlTool()
            bf = tool.load_bloom_filter(output_url)
            assert bf is None

    def test_load_nonexistent_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_url = parse_url(os.path.join(tmpdir, "nonexistent.avro"))
            tool = CrawlTool()
            bf = tool.load_bloom_filter(output_url)
            assert bf is None


class TestCrawlToolLoadRequests:
    def test_load_text_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_url = parse_url(os.path.join(tmpdir, "requests.txt"))
            with input_url.with_mode("w") as f:
                f.write("https://example.com/page1\n")
                f.write("https://example.com/page2\n")

            tool = CrawlTool()
            urls = list(tool.load_requests(input_url, InputFormat.TEXT))
            assert len(urls) == 2
            assert "https://example.com/page1" in urls
            assert "https://example.com/page2" in urls

    def test_load_text_format_empty_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_url = parse_url(os.path.join(tmpdir, "requests.txt"))
            with input_url.with_mode("w") as f:
                f.write("https://example.com/page1\n")
                f.write("\n")
                f.write("https://example.com/page2\n")

            tool = CrawlTool()
            urls = list(tool.load_requests(input_url, InputFormat.TEXT))
            assert len(urls) == 3
            assert "https://example.com/page1" in urls
            assert "" in urls
            assert "https://example.com/page2" in urls

    def test_load_json_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_url = parse_url(os.path.join(tmpdir, "requests.jsonl"))
            with input_url.with_mode("w") as f:
                f.write(json.dumps({"url": "https://example.com/page1"}) + "\n")
                f.write(json.dumps({"url": "https://example.com/page2"}) + "\n")

            tool = CrawlTool()
            urls = list(tool.load_requests(input_url, InputFormat.JSON))
            assert len(urls) == 2

    def test_load_avro_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_url = parse_url(os.path.join(tmpdir, "requests.avro"))

            schema = avro_schema(
                {
                    "name": "Request",
                    "type": "record",
                    "fields": [{"name": "url", "type": "string"}],
                }
            )
            with avro_writer(input_url.with_mode("wb"), schema) as writer:
                writer.append({"url": "https://example.com/page1"})
                writer.append({"url": "https://example.com/page2"})

            tool = CrawlTool()
            urls = list(tool.load_requests(input_url, InputFormat.AVRO))
            assert len(urls) == 2

    def test_load_with_bloom_filter_excludes_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_url = parse_url(os.path.join(tmpdir, "requests.txt"))
            with input_url.with_mode("w") as f:
                f.write("https://example.com/page1\n")
                f.write("https://example.com/page2\n")

            bf = BloomFilter(size=1000, hash_count=3)
            bf.add("example.com:/page1:")

            tool = CrawlTool()
            urls = list(
                tool.load_requests(input_url, InputFormat.TEXT, bloom_filter=bf)
            )
            assert len(urls) == 1
            assert "https://example.com/page2" in urls

    def test_load_avro_with_error_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_url = parse_url(os.path.join(tmpdir, "requests.avro"))

            schema = avro_schema(
                {
                    "name": "Page",
                    "type": "record",
                    "fields": [
                        {"name": "url", "type": "string"},
                        {"name": "error", "type": ["null", "string"], "default": None},
                    ],
                }
            )
            with avro_writer(input_url.with_mode("wb"), schema) as writer:
                writer.append({"url": "https://example.com/page1", "error": None})
                writer.append({"url": "https://example.com/page2", "error": "Failed"})

            tool = CrawlTool()
            urls = list(tool.load_requests(input_url, InputFormat.AVRO))
            assert len(urls) == 2


class TestCrawlToolStats:
    def test_default_stats(self):
        from rubbernecker.crawl.tool import CrawlToolStats

        stats = CrawlToolStats()
        assert stats.count_input == 0
        assert stats.count_output == 0
        assert stats.count_error == 0

    def test_stats_with_values(self):
        from rubbernecker.crawl.tool import CrawlToolStats

        stats = CrawlToolStats(count_input=10, count_output=8, count_error=2)
        assert stats.count_input == 10
        assert stats.count_output == 8
        assert stats.count_error == 2
