<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# Output Formats

All Rubbernecker commands that produce data write Avro files. This page
describes the schema for each command's output.

## Crawl Output (Raw HTML)

Produced by [`crawl`](commands/crawl.md). Each record represents one crawled URL.

| Field | Type | Description |
|---|---|---|
| `url` | string | Crawled URL |
| `timestamp` | long | Unix timestamp in milliseconds |
| `body` | string \| null | Raw HTML content |
| `error` | string \| null | Error message if the request failed |
| `metadata` | map \| null | Custom metadata |

## Parse Output (StandardPageParser)

Produced by [`parse`](commands/parse.md) using `rubbernecker.parse.standard.StandardPageParser`.

| Field | Type | Description |
|---|---|---|
| `url` | string | Page URL |
| `timestamp` | long | Crawl timestamp |
| `title` | string \| null | Page `<title>` |
| `content_length` | int | HTML content length in bytes |
| `body_text` | string \| null | Extracted visible text |
| `headers` | array \| null | H1–H6 elements, each with `level` (int) and `text` (string) |
| `links` | array \| null | Anchor elements, each with `text`, `url`, and `external` (bool) |

## Sitemap Output

Produced by [`sitemap`](commands/sitemap.md) when using `--output-format avro`.

| Field | Type | Description |
|---|---|---|
| `url` | string | Page URL |
| `lastmod` | string \| null | Last modification date (ISO 8601) |
| `changefreq` | string \| null | Suggested crawl frequency (e.g. `weekly`, `daily`) |
| `priority` | string \| null | Relative priority hint (0.0–1.0 as a string) |

When using `--save-sitemaps`, raw sitemap documents are stored using the same
`Page` schema as crawl output, with the raw XML in the `body` field.

## Viewing Avro Files

Convert any Avro file to JSON for inspection:

```bash
uv run avrokit tojson tmp/output.avro | jq .
```
