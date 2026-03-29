# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import logging
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

import requests
from avrokit import avro_schema, avro_writer, parse_url

from rubbernecker.base import AVRO_CODEC

logger = logging.getLogger(__name__)

# Namespace used in standard sitemap XML
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Reuse the same Page schema as crawl/fetch so --save-sitemaps output is
# compatible with downstream tools (parse, etc.).
PAGE_SCHEMA = avro_schema(
    {
        "name": "Page",
        "type": "record",
        "fields": [
            {"name": "url", "type": "string"},
            {"name": "timestamp", "type": "long"},
            {"name": "body", "type": ["null", "string"], "default": None},
            {"name": "error", "type": ["null", "string"], "default": None},
            {
                "name": "metadata",
                "type": [
                    "null",
                    {
                        "type": "map",
                        "values": ["null", "string"],
                    },
                ],
                "default": None,
            },
        ],
    }
)

# Schema for the --output Avro format.
# url is required (compatible with CrawlTool's InputFormat.AVRO);
# the standard sitemap metadata fields are optional.
ENTRY_SCHEMA = avro_schema(
    {
        "name": "SitemapEntry",
        "type": "record",
        "fields": [
            {"name": "url", "type": "string"},
            {"name": "lastmod", "type": ["null", "string"], "default": None},
            {"name": "changefreq", "type": ["null", "string"], "default": None},
            {"name": "priority", "type": ["null", "string"], "default": None},
        ],
    }
)


@dataclass
class SitemapEntry:
    """A single page URL entry from a sitemap <url> element."""

    url: str
    lastmod: str | None = None
    changefreq: str | None = None
    priority: str | None = None


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    AVRO = "avro"


@dataclass
class SitemapToolStats:
    count_input: int = 0
    count_sitemaps: int = 0
    count_output: int = 0
    count_error: int = 0


def _fetch_content(url: str) -> str:
    """Fetch URL or read local file; return text content."""
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    else:
        # Local file path via avrokit
        f_url = parse_url(url)
        with f_url.with_mode("r") as f:
            content = f.read()
        return content


def _is_robots_txt(url: str) -> bool:
    return urlparse(url).path.lower().endswith("robots.txt")


def _parse_robots(content: str) -> list[str]:
    """Extract Sitemap: directives from a robots.txt file."""
    urls = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("sitemap:"):
            sitemap_url = stripped[len("sitemap:") :].strip()
            if sitemap_url:
                urls.append(sitemap_url)
    logger.info("Parsed robots.txt: found %d sitemap directive(s)", len(urls))
    return urls


def _parse_sitemap_index(root: ET.Element) -> list[str]:
    """Extract <loc> values from a <sitemapindex> element."""
    locs = []
    for sitemap_el in root.findall(f"{{{_SITEMAP_NS}}}sitemap"):
        loc_el = sitemap_el.find(f"{{{_SITEMAP_NS}}}loc")
        if loc_el is not None and loc_el.text:
            locs.append(loc_el.text.strip())
    # Also try without namespace (non-standard but seen in the wild)
    for sitemap_el in root.findall("sitemap"):
        loc_el = sitemap_el.find("loc")
        if loc_el is not None and loc_el.text:
            locs.append(loc_el.text.strip())
    return locs


def _parse_urlset(root: ET.Element) -> list[SitemapEntry]:
    """Extract <url> entries (with all standard metadata) from a <urlset> element."""

    def _text(el: ET.Element, tag: str, ns: str | None = _SITEMAP_NS) -> str | None:
        child = el.find(f"{{{ns}}}{tag}") if ns else el.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        # Fallback: try without namespace
        if ns is not None:
            child = el.find(tag)
            if child is not None and child.text:
                return child.text.strip()
        return None

    entries: list[SitemapEntry] = []

    # Try namespaced elements first, then fall back to non-namespaced
    url_els = root.findall(f"{{{_SITEMAP_NS}}}url") or root.findall("url")

    for url_el in url_els:
        loc = _text(url_el, "loc")
        if not loc:
            continue
        entries.append(
            SitemapEntry(
                url=loc,
                lastmod=_text(url_el, "lastmod"),
                changefreq=_text(url_el, "changefreq"),
                priority=_text(url_el, "priority"),
            )
        )
    return entries


@dataclass
class _FetchResult:
    """Return value from a single-URL fetch worker."""

    url: str
    timestamp: int
    content: str | None
    error: str | None
    # Child sitemap URLs to enqueue for the next BFS wave
    child_urls: list[str] = field(default_factory=list)
    # Page entries discovered (leaf nodes)
    page_entries: list[SitemapEntry] = field(default_factory=list)


def _fetch_one(url: str) -> _FetchResult:
    """
    Fetch and parse a single sitemap/robots.txt URL.
    Returns a _FetchResult describing what was found — no shared state touched.
    """
    timestamp = int(time.time())
    content: str | None = None
    error: str | None = None

    try:
        content = _fetch_content(url)
    except Exception as e:
        error = str(e)
        logger.warning("Failed to fetch %s: %s", url, e)
        return _FetchResult(url=url, timestamp=timestamp, content=None, error=error)

    child_urls: list[str] = []
    page_entries: list[SitemapEntry] = []

    if _is_robots_txt(url):
        child_urls = _parse_robots(content)
    else:
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.warning("Failed to parse XML from %s: %s", url, e)
            return _FetchResult(
                url=url,
                timestamp=timestamp,
                content=content,
                error=str(e),
            )

        local_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

        if local_tag == "sitemapindex":
            child_urls = _parse_sitemap_index(root)
        elif local_tag == "urlset":
            page_entries = _parse_urlset(root)
        else:
            logger.warning("Unrecognised XML root <%s> in %s, skipping", local_tag, url)

    return _FetchResult(
        url=url,
        timestamp=timestamp,
        content=content,
        error=error,
        child_urls=child_urls,
        page_entries=page_entries,
    )


@dataclass
class CrawlResult:
    """The in-memory result of crawling one or more sitemaps."""

    entries: dict[str, SitemapEntry]  # keyed by URL for dedup
    stats: SitemapToolStats


def crawl_sitemap(
    urls: list[str],
    save_sitemaps_url_str: str | None = None,
    parallelism: int = 1,
) -> CrawlResult:
    """
    Fetch and parse one or more sitemap / robots.txt URLs recursively.

    Returns all discovered page entries in memory without writing any output
    file — callers can then pass the result to write_entries() in whatever
    format(s) they need, without re-fetching.

    Uses a BFS wave strategy so that the ThreadPoolExecutor workers never block
    waiting on further submissions — avoiding deadlocks.
    """
    stats = SitemapToolStats(count_input=len(urls))

    seen_sitemaps: set[str] = set()
    # Keyed by URL for deduplication; later entries overwrite earlier ones
    # (same URL in two sitemaps is uncommon, but we want deterministic output).
    page_entries: dict[str, SitemapEntry] = {}

    save_url = parse_url(save_sitemaps_url_str) if save_sitemaps_url_str else None
    sitemap_writer_ctx = None
    sitemap_writer: Any | None = None

    logger.info(
        "Starting sitemap crawl: %d input URL(s), parallelism=%d",
        len(urls),
        parallelism,
    )
    if save_sitemaps_url_str:
        logger.info("Saving raw sitemap documents to: %s", save_sitemaps_url_str)

    try:
        if save_url is not None:
            sitemap_writer_ctx = avro_writer(
                save_url.with_mode("a+b"), PAGE_SCHEMA, codec=AVRO_CODEC
            )
            sitemap_writer = sitemap_writer_ctx.__enter__()

        current_wave: list[str] = list(urls)
        wave_num = 0

        while current_wave:
            wave_num += 1
            # Deduplicate within the wave and against already-seen URLs
            to_fetch: list[str] = []
            for url in current_wave:
                if url not in seen_sitemaps:
                    seen_sitemaps.add(url)
                    to_fetch.append(url)

            if not to_fetch:
                logger.info("Wave %d: no new URLs to fetch, stopping", wave_num)
                break

            logger.info(
                "Wave %d: fetching %d URL(s) (%d skipped as already seen)",
                wave_num,
                len(to_fetch),
                len(current_wave) - len(to_fetch),
            )

            next_wave: list[str] = []

            with ThreadPoolExecutor(max_workers=parallelism) as executor:
                future_map = {executor.submit(_fetch_one, url): url for url in to_fetch}
                for future in as_completed(future_map):
                    try:
                        result = future.result()
                    except Exception as e:
                        logger.error("Unexpected error processing sitemap: %s", e)
                        stats.count_error += 1
                        continue

                    if result.error and result.content is None:
                        logger.error("Error fetching %s: %s", result.url, result.error)
                        stats.count_error += 1
                    else:
                        stats.count_sitemaps += 1
                        new_entries = [
                            e for e in result.page_entries if e.url not in page_entries
                        ]
                        for entry in result.page_entries:
                            page_entries[entry.url] = entry
                        logger.debug(
                            "Processed %s: +%d new page(s), %d child sitemap(s) enqueued",
                            result.url,
                            len(new_entries),
                            len(result.child_urls),
                        )
                        next_wave.extend(result.child_urls)

                    if sitemap_writer is not None:
                        sitemap_writer.append(
                            {
                                "url": result.url,
                                "timestamp": result.timestamp,
                                "body": result.content,
                                "error": result.error,
                                "metadata": None,
                            }
                        )

            logger.info(
                "Wave %d complete: %d total page(s) discovered, %d URL(s) in next wave",
                wave_num,
                len(page_entries),
                len(next_wave),
            )
            current_wave = next_wave

    finally:
        if sitemap_writer_ctx is not None:
            sitemap_writer_ctx.__exit__(None, None, None)

    logger.info(
        "Sitemap crawl complete: %d input(s), %d sitemap(s) fetched, "
        "%d URL(s) discovered, %d error(s)",
        stats.count_input,
        stats.count_sitemaps,
        len(page_entries),
        stats.count_error,
    )

    return CrawlResult(entries=page_entries, stats=stats)


def write_entries(
    crawl_result: CrawlResult,
    output_url_str: str,
    output_format: OutputFormat = OutputFormat.TEXT,
) -> int:
    """
    Write the entries from a CrawlResult to output_url_str in the requested
    format. Returns the number of entries written. Updates crawl_result.stats.
    """
    sorted_entries = sorted(crawl_result.entries.values(), key=lambda e: e.url)
    out_url = parse_url(output_url_str)

    logger.info(
        "Writing %d URL(s) to %s (format: %s)",
        len(sorted_entries),
        output_url_str,
        output_format,
    )

    if output_format == OutputFormat.TEXT:
        with out_url.with_mode("w") as f:
            for entry in sorted_entries:
                f.write(entry.url + "\n")
    elif output_format == OutputFormat.JSON:
        with out_url.with_mode("w") as f:
            for entry in sorted_entries:
                record: dict[str, Any] = {"url": entry.url}
                if entry.lastmod is not None:
                    record["lastmod"] = entry.lastmod
                if entry.changefreq is not None:
                    record["changefreq"] = entry.changefreq
                if entry.priority is not None:
                    record["priority"] = entry.priority
                f.write(json.dumps(record) + "\n")
    elif output_format == OutputFormat.AVRO:
        with avro_writer(
            out_url.with_mode("a+b"), ENTRY_SCHEMA, codec=AVRO_CODEC
        ) as writer:
            for entry in sorted_entries:
                writer.append(
                    {
                        "url": entry.url,
                        "lastmod": entry.lastmod,
                        "changefreq": entry.changefreq,
                        "priority": entry.priority,
                    }
                )

    crawl_result.stats.count_output = len(sorted_entries)
    logger.info(
        "Write complete: %d URL(s) written to %s", len(sorted_entries), output_url_str
    )
    return len(sorted_entries)


def run_sitemap(
    urls: list[str],
    output_url_str: str,
    output_format: OutputFormat = OutputFormat.TEXT,
    save_sitemaps_url_str: str | None = None,
    parallelism: int = 1,
) -> SitemapToolStats:
    """Crawl sitemaps and write discovered URLs to output_url_str."""
    logger.info(
        "run_sitemap: urls=%s output=%s format=%s save_sitemaps=%s parallelism=%d",
        urls,
        output_url_str,
        output_format,
        save_sitemaps_url_str,
        parallelism,
    )
    crawl_result = crawl_sitemap(
        urls=urls,
        save_sitemaps_url_str=save_sitemaps_url_str,
        parallelism=parallelism,
    )
    write_entries(crawl_result, output_url_str, output_format)
    logger.info(
        "Sitemap complete: %d input(s), %d sitemap(s) fetched, "
        "%d URL(s) written, %d error(s)",
        crawl_result.stats.count_input,
        crawl_result.stats.count_sitemaps,
        crawl_result.stats.count_output,
        crawl_result.stats.count_error,
    )
    return crawl_result.stats


class SitemapTool:
    def name(self) -> str:
        return "sitemap"

    def configure(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(
            self.name(), help="Generate a crawl from a sitemap."
        )
        parser.add_argument(
            "urls",
            nargs="+",
            help=(
                "One or more sitemap URLs, sitemap index URLs, or robots.txt URLs. "
                "Local file paths are also accepted."
            ),
        )
        parser.add_argument(
            "--output",
            required=True,
            help="Destination file for discovered page URLs.",
        )
        parser.add_argument(
            "--output-format",
            choices=[f.value for f in OutputFormat],
            default=OutputFormat.TEXT.value,
            help="Output format: text (default), json (JSONL), or avro.",
        )
        parser.add_argument(
            "--save-sitemaps",
            default=None,
            help=(
                "If provided, save each fetched sitemap/robots.txt document as an "
                "Avro Page record (same schema as the crawl tool) to this path."
            ),
        )
        parser.add_argument(
            "--parallelism",
            type=int,
            default=1,
            help="Number of concurrent sitemap fetches (default: 1).",
        )

    def run(self, args: argparse.Namespace) -> None:
        run_sitemap(
            urls=args.urls,
            output_url_str=args.output,
            output_format=OutputFormat(args.output_format),
            save_sitemaps_url_str=args.save_sitemaps,
            parallelism=args.parallelism,
        )
