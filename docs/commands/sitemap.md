<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# `rubbernecker sitemap`

Discover page URLs from sitemaps, sitemap indexes, or `robots.txt` files and
write them to an output file ready to feed into `crawl`.

Sitemap indexes are handled automatically by recursively fetching all linked
sitemaps. All discovered URLs are deduplicated before writing.

## Syntax

```bash
uv run rubbernecker sitemap URL [URL ...] --output OUTPUT [OPTIONS]
```

## Arguments

- `URL` - One or more sitemap URLs, sitemap index URLs, `robots.txt` URLs, or
  local file paths.

## Options

- `--output PATH` *(required)* - Destination file for discovered page URLs.
- `--output-format FORMAT` - Output format (default: `text`):
  - `text` — one URL per line; feeds directly into `crawl` as a URL list.
  - `json` — JSONL; one `{"url": ..., "lastmod": ..., "changefreq": ..., "priority": ...}` object per line (metadata keys omitted when absent).
  - `avro` — Avro records compatible with `crawl --input_format AVRO`.
- `--save-sitemaps PATH` - Save each fetched sitemap/robots.txt document as an
  Avro `Page` record (same schema as `crawl`) to this path. Useful for
  archiving or inspecting raw sitemap XML.
- `--parallelism N` - Number of concurrent sitemap fetches (default: `1`).

## Examples

```bash
# Discover all URLs from a sitemap index, write a plain URL list
uv run rubbernecker sitemap https://pypi.org/sitemap.xml \
    --output tmp/pypi-urls.txt

# JSONL output with metadata (lastmod, changefreq, priority)
uv run rubbernecker sitemap https://pypi.org/sitemap.xml \
    --output tmp/pypi-urls.jsonl \
    --output-format json

# Avro output, compatible with crawl --input_format AVRO
uv run rubbernecker sitemap https://pypi.org/sitemap.xml \
    --output tmp/pypi-urls.avro \
    --output-format avro

# Extract sitemaps from robots.txt
uv run rubbernecker sitemap https://pypi.org/robots.txt \
    --output tmp/pypi-urls.txt

# Multiple input URLs, parallel fetching, save raw sitemap documents
uv run rubbernecker sitemap \
    https://pypi.org/sitemap.xml \
    https://docs.python.org/sitemap.xml \
    --output tmp/combined-urls.txt \
    --save-sitemaps tmp/sitemaps.avro \
    --parallelism 8
```

## Full Pipeline: Discover then Crawl

```bash
uv run rubbernecker sitemap https://pypi.org/sitemap.xml \
    --output tmp/pypi-urls.txt \
    --parallelism 4

uv run rubbernecker crawl tmp/pypi-urls.txt tmp/pypi-raw.avro
```

## Output Format

See [output-formats.md](../output-formats.md#sitemap-output) for schema details.
