# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest
from avrokit import avro_records, parse_url

from rubbernecker.sitemap.tool import (
    OutputFormat,
    SitemapTool,
    _is_robots_txt,
    _parse_robots,
    _parse_sitemap_index,
    _parse_urlset,
    crawl_sitemap,
    run_sitemap,
    write_entries,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

URLSET_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
  <url><loc>https://example.com/page3</loc></url>
</urlset>
"""

URLSET_RICH_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/page1</loc>
    <lastmod>2024-01-15</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://example.com/page2</loc>
    <lastmod>2024-02-01</lastmod>
  </url>
  <url>
    <loc>https://example.com/page3</loc>
  </url>
</urlset>
"""

SITEMAP_INDEX_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-a.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-b.xml</loc></sitemap>
</sitemapindex>
"""

URLSET_A_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a/1</loc></url>
  <url><loc>https://example.com/a/2</loc></url>
</urlset>
"""

URLSET_B_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/b/1</loc></url>
</urlset>
"""

ROBOTS_TXT = """\
User-agent: *
Disallow: /private/

Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap2.xml
"""

ROBOTS_TXT_NO_SITEMAP = """\
User-agent: *
Disallow: /private/
"""

# ---------------------------------------------------------------------------
# Unit tests: pure parsing helpers
# ---------------------------------------------------------------------------


def test_is_robots_txt_http():
    assert _is_robots_txt("https://example.com/robots.txt") is True


def test_is_robots_txt_local():
    assert _is_robots_txt("/tmp/robots.txt") is True


def test_is_robots_txt_case_insensitive():
    assert _is_robots_txt("https://example.com/Robots.TXT") is True


def test_is_robots_txt_false():
    assert _is_robots_txt("https://example.com/sitemap.xml") is False


def test_parse_robots_extracts_all_sitemaps():
    result = _parse_robots(ROBOTS_TXT)
    assert result == [
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap2.xml",
    ]


def test_parse_robots_no_sitemaps():
    result = _parse_robots(ROBOTS_TXT_NO_SITEMAP)
    assert result == []


def test_parse_sitemap_index():
    root = ET.fromstring(SITEMAP_INDEX_XML)
    result = _parse_sitemap_index(root)
    assert result == [
        "https://example.com/sitemap-a.xml",
        "https://example.com/sitemap-b.xml",
    ]


def test_parse_urlset():
    root = ET.fromstring(URLSET_XML)
    result = _parse_urlset(root)
    assert [e.url for e in result] == [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3",
    ]
    # No metadata in this fixture
    for entry in result:
        assert entry.lastmod is None
        assert entry.changefreq is None
        assert entry.priority is None


def test_parse_urlset_metadata():
    root = ET.fromstring(URLSET_RICH_XML)
    result = _parse_urlset(root)
    assert len(result) == 3

    assert result[0].url == "https://example.com/page1"
    assert result[0].lastmod == "2024-01-15"
    assert result[0].changefreq == "weekly"
    assert result[0].priority == "0.8"

    assert result[1].url == "https://example.com/page2"
    assert result[1].lastmod == "2024-02-01"
    assert result[1].changefreq is None
    assert result[1].priority is None

    assert result[2].url == "https://example.com/page3"
    assert result[2].lastmod is None


def test_parse_urlset_no_namespace():
    xml = """\
<urlset>
  <url><loc>https://example.com/nons</loc></url>
</urlset>"""
    root = ET.fromstring(xml)
    result = _parse_urlset(root)
    assert len(result) == 1
    assert result[0].url == "https://example.com/nons"


# ---------------------------------------------------------------------------
# Unit tests: run_sitemap with mocked HTTP
# ---------------------------------------------------------------------------


def _make_fetch_map(mapping: dict[str, str]):
    """Return a side_effect function for patching _fetch_content."""

    def _fetch(url: str) -> str:
        if url in mapping:
            return mapping[url]
        raise ValueError(f"Unexpected URL in test: {url}")

    return _fetch


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_simple_urlset(mock_fetch, tmp_path):
    mock_fetch.side_effect = _make_fetch_map(
        {"https://example.com/sitemap.xml": URLSET_XML}
    )
    output = str(tmp_path / "out.txt")
    stats = run_sitemap(
        urls=["https://example.com/sitemap.xml"],
        output_url_str=output,
        output_format=OutputFormat.TEXT,
    )
    assert stats.count_input == 1
    assert stats.count_sitemaps == 1
    assert stats.count_output == 3
    assert stats.count_error == 0

    with open(output) as f:
        lines = [line.strip() for line in f if line.strip()]
    assert sorted(lines) == [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3",
    ]


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_index_drills_down(mock_fetch, tmp_path):
    mock_fetch.side_effect = _make_fetch_map(
        {
            "https://example.com/sitemap-index.xml": SITEMAP_INDEX_XML,
            "https://example.com/sitemap-a.xml": URLSET_A_XML,
            "https://example.com/sitemap-b.xml": URLSET_B_XML,
        }
    )
    output = str(tmp_path / "out.txt")
    stats = run_sitemap(
        urls=["https://example.com/sitemap-index.xml"],
        output_url_str=output,
    )
    assert stats.count_sitemaps == 3  # index + a + b
    assert stats.count_output == 3
    assert stats.count_error == 0

    with open(output) as f:
        lines = [line.strip() for line in f if line.strip()]
    assert sorted(lines) == [
        "https://example.com/a/1",
        "https://example.com/a/2",
        "https://example.com/b/1",
    ]


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_robots_txt(mock_fetch, tmp_path):
    mock_fetch.side_effect = _make_fetch_map(
        {
            "https://example.com/robots.txt": ROBOTS_TXT,
            "https://example.com/sitemap.xml": URLSET_XML,
            "https://example.com/sitemap2.xml": URLSET_B_XML,
        }
    )
    output = str(tmp_path / "out.txt")
    stats = run_sitemap(
        urls=["https://example.com/robots.txt"],
        output_url_str=output,
    )
    # robots.txt itself counts as a sitemap fetch; plus the two linked sitemaps
    assert stats.count_sitemaps == 3
    assert stats.count_output == 4  # 3 from sitemap.xml + 1 from sitemap2.xml
    assert stats.count_error == 0


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_deduplicates_urls(mock_fetch, tmp_path):
    """Same page URL appearing in two different sitemaps should only appear once."""
    duplicate_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page1</loc></url>
</urlset>"""
    mock_fetch.side_effect = _make_fetch_map(
        {"https://example.com/sitemap.xml": duplicate_xml}
    )
    output = str(tmp_path / "out.txt")
    stats = run_sitemap(
        urls=["https://example.com/sitemap.xml"],
        output_url_str=output,
    )
    assert stats.count_output == 1


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_deduplicates_across_inputs(mock_fetch, tmp_path):
    """Two top-level inputs pointing to the same URL should only be fetched once."""
    mock_fetch.side_effect = _make_fetch_map(
        {"https://example.com/sitemap.xml": URLSET_XML}
    )
    output = str(tmp_path / "out.txt")
    stats = run_sitemap(
        urls=[
            "https://example.com/sitemap.xml",
            "https://example.com/sitemap.xml",
        ],
        output_url_str=output,
    )
    assert mock_fetch.call_count == 1
    assert stats.count_output == 3


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_fetch_error_continues(mock_fetch, tmp_path):
    """A fetch error on one sitemap should not abort the run."""

    def _fetch(url: str) -> str:
        if url == "https://example.com/sitemap-ok.xml":
            return URLSET_XML
        raise requests.exceptions.ConnectionError("network error")

    import requests

    mock_fetch.side_effect = _fetch
    output = str(tmp_path / "out.txt")
    stats = run_sitemap(
        urls=[
            "https://example.com/sitemap-ok.xml",
            "https://example.com/sitemap-bad.xml",
        ],
        output_url_str=output,
    )
    assert stats.count_error == 1
    assert stats.count_output == 3


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_output_format_json(mock_fetch, tmp_path):
    import json as _json

    mock_fetch.side_effect = _make_fetch_map(
        {"https://example.com/sitemap.xml": URLSET_RICH_XML}
    )
    output = str(tmp_path / "out.jsonl")
    run_sitemap(
        urls=["https://example.com/sitemap.xml"],
        output_url_str=output,
        output_format=OutputFormat.JSON,
    )
    with open(output) as f:
        records = [_json.loads(line) for line in f if line.strip()]
    assert len(records) == 3
    assert all("url" in r for r in records)
    assert sorted(r["url"] for r in records) == [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3",
    ]
    # page1 has all metadata fields
    page1 = next(r for r in records if r["url"] == "https://example.com/page1")
    assert page1["lastmod"] == "2024-01-15"
    assert page1["changefreq"] == "weekly"
    assert page1["priority"] == "0.8"
    # page2 has only lastmod
    page2 = next(r for r in records if r["url"] == "https://example.com/page2")
    assert page2["lastmod"] == "2024-02-01"
    assert "changefreq" not in page2
    assert "priority" not in page2
    # page3 has no metadata fields at all
    page3 = next(r for r in records if r["url"] == "https://example.com/page3")
    assert "lastmod" not in page3


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_output_format_avro(mock_fetch, tmp_path):
    mock_fetch.side_effect = _make_fetch_map(
        {"https://example.com/sitemap.xml": URLSET_RICH_XML}
    )
    output = str(tmp_path / "out.avro")
    run_sitemap(
        urls=["https://example.com/sitemap.xml"],
        output_url_str=output,
        output_format=OutputFormat.AVRO,
    )
    records = list(avro_records(parse_url(output)))
    assert len(records) == 3
    assert sorted(r["url"] for r in records) == [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3",
    ]
    page1 = next(r for r in records if r["url"] == "https://example.com/page1")
    assert page1["lastmod"] == "2024-01-15"
    assert page1["changefreq"] == "weekly"
    assert page1["priority"] == "0.8"
    page3 = next(r for r in records if r["url"] == "https://example.com/page3")
    assert page3["lastmod"] is None
    assert page3["changefreq"] is None
    assert page3["priority"] is None


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_save_sitemaps(mock_fetch, tmp_path):
    mock_fetch.side_effect = _make_fetch_map(
        {
            "https://example.com/sitemap-index.xml": SITEMAP_INDEX_XML,
            "https://example.com/sitemap-a.xml": URLSET_A_XML,
            "https://example.com/sitemap-b.xml": URLSET_B_XML,
        }
    )
    output = str(tmp_path / "out.txt")
    sitemaps_output = str(tmp_path / "sitemaps.avro")
    run_sitemap(
        urls=["https://example.com/sitemap-index.xml"],
        output_url_str=output,
        save_sitemaps_url_str=sitemaps_output,
    )
    records = list(avro_records(parse_url(sitemaps_output)))
    saved_urls = {r["url"] for r in records}
    assert saved_urls == {
        "https://example.com/sitemap-index.xml",
        "https://example.com/sitemap-a.xml",
        "https://example.com/sitemap-b.xml",
    }
    # Each record has the raw XML body
    for r in records:
        assert r["body"] is not None
        assert r["error"] is None


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_save_sitemaps_records_errors(mock_fetch, tmp_path):
    """Error records should be saved with error set and body null."""

    def _fetch(url: str) -> str:
        raise ValueError("oops")

    mock_fetch.side_effect = _fetch
    output = str(tmp_path / "out.txt")
    sitemaps_output = str(tmp_path / "sitemaps.avro")
    run_sitemap(
        urls=["https://example.com/sitemap.xml"],
        output_url_str=output,
        save_sitemaps_url_str=sitemaps_output,
    )
    records = list(avro_records(parse_url(sitemaps_output)))
    assert len(records) == 1
    assert records[0]["error"] is not None
    assert records[0]["body"] is None


@patch("rubbernecker.sitemap.tool._fetch_content")
def test_run_sitemap_parallelism(mock_fetch, tmp_path):
    """Parallel mode should still produce the same results."""
    mock_fetch.side_effect = _make_fetch_map(
        {
            "https://example.com/sitemap-index.xml": SITEMAP_INDEX_XML,
            "https://example.com/sitemap-a.xml": URLSET_A_XML,
            "https://example.com/sitemap-b.xml": URLSET_B_XML,
        }
    )
    output = str(tmp_path / "out.txt")
    stats = run_sitemap(
        urls=["https://example.com/sitemap-index.xml"],
        output_url_str=output,
        parallelism=4,
    )
    assert stats.count_output == 3
    assert stats.count_error == 0


# ---------------------------------------------------------------------------
# SitemapTool.configure smoke test
# ---------------------------------------------------------------------------


def test_sitemap_tool_configure():
    import argparse

    tool = SitemapTool()
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    tool.configure(subparsers)

    args = parser.parse_args(
        [
            "sitemap",
            "https://example.com/sitemap.xml",
            "--output",
            "/tmp/out.txt",
            "--output-format",
            "json",
            "--parallelism",
            "4",
        ]
    )
    assert args.urls == ["https://example.com/sitemap.xml"]
    assert args.output == "/tmp/out.txt"
    assert args.output_format == "json"
    assert args.parallelism == 4
    assert args.save_sitemaps is None


def test_sitemap_tool_configure_save_sitemaps():
    import argparse

    tool = SitemapTool()
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    tool.configure(subparsers)

    args = parser.parse_args(
        [
            "sitemap",
            "https://example.com/sitemap.xml",
            "--output",
            "/tmp/out.txt",
            "--save-sitemaps",
            "/tmp/sitemaps.avro",
        ]
    )
    assert args.save_sitemaps == "/tmp/sitemaps.avro"


# ---------------------------------------------------------------------------
# Integration test: real HTTP (skipped by default)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_run_sitemap_integration_all_formats(tmp_path):
    """
    Crawl https://pypi.org/sitemap.xml once, then write the same CrawlResult
    in all three output formats and verify each one is well-formed and
    consistent.
    """
    import json as _json

    result = crawl_sitemap(
        urls=["https://pypi.org/sitemap.xml"],
        parallelism=4,
    )

    assert result.stats.count_output == 0, "count_output not set until write_entries"
    assert result.stats.count_sitemaps > 0
    assert result.stats.count_error == 0
    assert len(result.entries) > 0

    expected_count = len(result.entries)
    expected_urls = sorted(result.entries.keys())

    # --- text ---
    text_out = str(tmp_path / "out.txt")
    n = write_entries(result, text_out, OutputFormat.TEXT)
    assert n == expected_count
    with open(text_out) as f:
        text_lines = [line.strip() for line in f if line.strip()]
    assert text_lines == expected_urls

    # --- json ---
    json_out = str(tmp_path / "out.jsonl")
    n = write_entries(result, json_out, OutputFormat.JSON)
    assert n == expected_count
    with open(json_out) as f:
        json_records = [_json.loads(line) for line in f if line.strip()]
    assert len(json_records) == expected_count
    assert [r["url"] for r in json_records] == expected_urls
    # All records must have a url key; metadata keys present only when non-null
    for r in json_records:
        assert "url" in r
        for key in ("lastmod", "changefreq", "priority"):
            if key in r:
                assert isinstance(r[key], str)

    # --- avro ---
    avro_out = str(tmp_path / "out.avro")
    n = write_entries(result, avro_out, OutputFormat.AVRO)
    assert n == expected_count
    avro_recs = list(avro_records(parse_url(avro_out)))
    assert len(avro_recs) == expected_count
    assert sorted(r["url"] for r in avro_recs) == expected_urls
    # Avro always has all fields (null when absent)
    for r in avro_recs:
        assert "url" in r
        assert "lastmod" in r
        assert "changefreq" in r
        assert "priority" in r
