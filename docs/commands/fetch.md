<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# `rubbernecker fetch`

Download assets from a list of URLs.

## Syntax

```bash
uv run rubbernecker fetch [OPTIONS] INPUT_URL OUTPUT_URL
```

## Arguments

- `INPUT_URL` - File containing URLs to fetch
- `OUTPUT_URL` - Path where fetched data will be saved

## Examples

```bash
uv run rubbernecker fetch tmp/urls.txt tmp/output/
```
