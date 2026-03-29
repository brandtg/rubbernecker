<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# `rubbernecker crawl`

Crawl web pages and save raw HTML to Avro files.

## Syntax

```bash
uv run rubbernecker crawl [OPTIONS] INPUT_URL OUTPUT_URL
```

## Arguments

- `INPUT_URL` - File containing URLs to crawl (text, JSON, or Avro format)
- `OUTPUT_URL` - Path where crawled data will be saved (Avro format)

## Options

- `--input_format FORMAT` - Input file format: `TEXT`, `JSON`, or `AVRO` (default: `TEXT`)
- `--max_depth N` - Maximum crawl depth for following links (default: `0`)
- `--max_retries N` - Retry failed requests up to N times
- `--sleep_success SECONDS` - Wait time after successful requests
- `--sleep_error SECONDS` - Wait time after errors
- `--load_actions FILE` - Actions to perform after page load (see [actions.md](../actions.md))
- `--crawl_actions FILE` - Actions to discover and crawl additional links (see [actions.md](../actions.md))
- `--use_bloom_filter` - Skip duplicate URLs (useful for large crawls)
- `--max_errors N` - Stop after N errors
- `--interactive` - Prompt before each crawl action

## Examples

```bash
# Basic crawl
uv run rubbernecker crawl tmp/urls.txt tmp/output.avro

# Crawl with depth (follow links up to 2 levels)
uv run rubbernecker crawl tmp/urls.txt tmp/output.avro --max_depth 2

# Crawl with custom actions
uv run rubbernecker crawl tmp/urls.txt tmp/output.avro \
    --load_actions tmp/load-actions.txt \
    --crawl_actions tmp/crawl-actions.txt

# Crawl with error handling
uv run rubbernecker crawl tmp/urls.txt tmp/output.avro \
    --max_retries 3 \
    --max_errors 10 \
    --sleep_error 5
```

## Full Pipeline Example

Complete example crawling Hacker News with actions:

```bash
mkdir -p tmp

cat > tmp/requests.txt << EOF
https://news.ycombinator.com/
EOF

cat > tmp/load-actions.txt << EOF
[news\.ycombinator\.com]
SLEEP 1
SCROLL 500
EOF

cat > tmp/crawl-actions.txt << EOF
[news\.ycombinator\.com]
CLICK a.morelink
EOF

uv run rubbernecker crawl tmp/requests.txt tmp/hn-raw.avro \
    --load_actions tmp/load-actions.txt \
    --crawl_actions tmp/crawl-actions.txt \
    --max_depth 2 \
    --max_retries 2 \
    --sleep_success 1

uv run rubbernecker parse rubbernecker.parse.standard.StandardPageParser \
    tmp/hn-raw.avro tmp/hn-parsed.avro

uv run avrokit tojson tmp/hn-parsed.avro | jq '.title, .links | length'
```

## Output Format

See [output-formats.md](../output-formats.md#crawl-output-raw-html) for the Avro schema.

## Troubleshooting

**Memory issues with large crawls:**

- Use `--use_bloom_filter` to reduce memory for duplicate detection
- Process in smaller batches with multiple crawl commands
