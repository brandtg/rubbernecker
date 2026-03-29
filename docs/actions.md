<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# Action Scripts

Action scripts define automated interactions with web pages using CSS selectors.
They are passed to `crawl` via `--load_actions` and `--crawl_actions`.

- **`--load_actions`** — Actions run after each page finishes loading (e.g. scroll, wait, fill forms).
- **`--crawl_actions`** — Actions that discover additional URLs to crawl (e.g. click a "next page" link).

## Format

```
[url_pattern_regex]
ACTION_NAME selector_or_arg extra_arg
ACTION_NAME selector_or_arg extra_arg
...
```

- The `[url_pattern_regex]` header is a regular expression matched against the
  current page URL. Actions beneath it only run on matching pages.
- Multiple URL pattern blocks can appear in one file.

## Available Actions

| Action | Arguments | Description |
|---|---|---|
| `SLEEP` | `seconds` | Wait for the specified number of seconds |
| `SCROLL` | `pixels` | Scroll the page vertically by `pixels` |
| `INPUT` | `selector text` | Fill a form input matching `selector` with `text` |
| `CLICK` | `selector` | Click an element matching `selector` |
| `CLICK_IF_EXISTS` | `selector` | Click the element only if it exists on the page |

## Examples

### Load Actions

Stabilise a page before grabbing its HTML (pass with `--load_actions`):

```
[news\.ycombinator\.com]
SLEEP 2
SCROLL 500
SLEEP 1
```

### Crawl Actions

Discover additional URLs by clicking pagination (pass with `--crawl_actions`):

```
[news\.ycombinator\.com]
CLICK a.morelink
```

This clicks the "More" link on Hacker News, causing the crawler to follow the
newly loaded page URL.

### Form Login

```
[example\.com/login]
INPUT #username myuser
INPUT #password mypassword
CLICK button[type=submit]
SLEEP 2
```

## Usage

```bash
uv run rubbernecker crawl tmp/urls.txt tmp/output.avro \
    --load_actions tmp/load-actions.txt \
    --crawl_actions tmp/crawl-actions.txt
```
