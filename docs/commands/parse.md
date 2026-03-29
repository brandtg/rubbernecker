<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# `rubbernecker parse`

Extract structured data from crawled HTML using a parser class.

## Syntax

```bash
uv run rubbernecker parse PARSER_CLASS INPUT_URL OUTPUT_URL
```

## Arguments

- `PARSER_CLASS` - Fully qualified parser class name
- `INPUT_URL` - Avro file produced by the `crawl` command
- `OUTPUT_URL` - Path for parsed output (Avro format)

## Available Parsers

### `rubbernecker.parse.standard.StandardPageParser`

Extracts common page elements:

- Page title
- Headers (H1–H6) with level and text
- Links with text, URL, and external flag
- Body text content

## Examples

```bash
# Parse with the standard parser
uv run rubbernecker parse rubbernecker.parse.standard.StandardPageParser \
    tmp/raw.avro tmp/parsed.avro

# View parsed results
uv run avrokit tojson tmp/parsed.avro | jq .
```

## Output Format

See [output-formats.md](../output-formats.md#parse-output-standardpageparser) for the Avro schema.

## Writing a Custom Parser

Implement a class with a `parse(page)` method that accepts a raw `Page` record
and returns a parsed record. Pass the fully qualified class name as `PARSER_CLASS`.
