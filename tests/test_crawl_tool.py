# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest
from avrokit import avro_schema, avro_writer, parse_url
from selenium.common.exceptions import TimeoutException

from rubbernecker.crawl.bloomfilter import BloomFilter
from rubbernecker.crawl.tool import CrawlTool, InputFormat, SeleniumDriver


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


class TestSeleniumDriver:
    def _mock_chrome(self, monkeypatch) -> tuple[list, list]:
        """Patch webdriver.Chrome to record options and return MagicMocks."""
        created_options: list = []
        created_drivers: list = []

        def fake_chrome(options=None):
            mock_driver = MagicMock()
            created_options.append(options)
            created_drivers.append(mock_driver)
            return mock_driver

        monkeypatch.setattr("rubbernecker.crawl.tool.webdriver.Chrome", fake_chrome)
        return created_options, created_drivers

    def test_default_options(self, monkeypatch):
        created_options, created_drivers = self._mock_chrome(monkeypatch)
        driver = SeleniumDriver()
        assert created_options[0].arguments == ["--incognito", "--lang=en-US"]
        assert created_drivers[0] is driver.driver

    def test_headless_and_proxy_options(self, monkeypatch):
        created_options, _ = self._mock_chrome(monkeypatch)
        SeleniumDriver(headless=True, proxy_server="http://localhost:3128")
        args = created_options[0].arguments
        assert "--headless=new" in args
        assert "--proxy-server=http://localhost:3128" in args

    def test_activate_cdp_mode(self, monkeypatch):
        _, created_drivers = self._mock_chrome(monkeypatch)
        driver = SeleniumDriver()
        mock_driver = created_drivers[0]
        driver.activate_cdp_mode("https://example.com/")
        mock_driver.execute_cdp_cmd.assert_called_once_with(
            "Page.navigate", {"url": "https://example.com/"}
        )

    def test_wait_for_ready_state_complete(self, monkeypatch):
        _, created_drivers = self._mock_chrome(monkeypatch)
        driver = SeleniumDriver()
        mock_driver = created_drivers[0]
        mock_driver.execute_script.return_value = "complete"
        driver.wait_for_ready_state_complete(timeout=1)

    def test_wait_for_ready_state_complete_timeout(self, monkeypatch):
        _, created_drivers = self._mock_chrome(monkeypatch)
        driver = SeleniumDriver()
        mock_driver = created_drivers[0]
        mock_driver.execute_script.return_value = "loading"
        with pytest.raises(TimeoutException):
            driver.wait_for_ready_state_complete(timeout=0.1)

    def test_quit_ignores_errors_and_is_idempotent(self, monkeypatch):
        _, created_drivers = self._mock_chrome(monkeypatch)
        driver = SeleniumDriver()
        mock_driver = created_drivers[0]
        mock_driver.quit.side_effect = Exception("already dead")
        driver.quit()
        assert driver.driver is None
        driver.quit()

    def test_restart_creates_new_driver(self, monkeypatch):
        created_options, created_drivers = self._mock_chrome(monkeypatch)
        driver = SeleniumDriver(headless=True)
        driver.restart()
        assert created_drivers[0] is not created_drivers[1]
        assert driver.driver is created_drivers[1]
        assert len(created_options) == 2

    def test_context_manager_quits(self, monkeypatch):
        self._mock_chrome(monkeypatch)
        with SeleniumDriver() as driver:
            pass
        assert driver.driver is None
