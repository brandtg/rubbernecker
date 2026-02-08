<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# Rubbernecker

A powerful web scraping engine built with Python and SeleniumBase that crawls web pages, stores raw HTML, and parses structured data. Rubbernecker supports configurable page actions, depth-based crawling, and proxy integration.

## Overview

Rubbernecker provides four main commands:

- **`chrome`** - Launch a Chrome browser instance with debugging capabilities
- **`crawl`** - Scrape websites and save raw HTML to Avro files
- **`parse`** - Extract structured data from crawled HTML
- **`proxy`** - Run a local proxy server for routing requests

## Installation

### Prerequisites

**Python 3.12+**

Rubbernecker requires Python 3.12 or higher.

**Google Chrome**

Rubbernecker uses SeleniumBase with Chrome for web crawling.

_macOS:_

```bash
brew install --cask google-chrome
```

_Fedora/RHEL (including WSL 2):_

```bash
sudo dnf install -y fedora-workstation-repositories
sudo dnf config-manager setopt google-chrome.enabled=1
sudo dnf install -y google-chrome-stable
```

_Ubuntu/Debian:_

```bash
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable
```

### Setup

**Install dependencies and set up environment:**

```bash
make install
```

Or manually:

```bash
poetry env use python3.12
poetry install
```

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for a step-by-step tutorial to get up and running in minutes.

## Commands

### `rubbernecker chrome`

Launch a Chrome browser instance with DevTools Protocol enabled.

**Options:**

- `--headless` - Run Chrome in headless mode (no GUI)
- `--chrome_debug_port PORT` - Port for Chrome DevTools Protocol (default: 9222)
- `--proxy_server URL` - Route traffic through a proxy server

**Examples:**

```bash
# Launch Chrome with visual interface
poetry run rubbernecker chrome

# Launch headless Chrome on custom port
poetry run rubbernecker chrome --headless --chrome_debug_port 9223

# Launch Chrome through a proxy
poetry run rubbernecker chrome --proxy_server "http://localhost:3128"
```

### `rubbernecker crawl`

Crawl web pages and save raw HTML to Avro files.

**Syntax:**

```bash
rubbernecker crawl [OPTIONS] INPUT_URL OUTPUT_URL
```

**Arguments:**

- `INPUT_URL` - File containing URLs to crawl (text, JSON, or Avro format)
- `OUTPUT_URL` - Path where crawled data will be saved (Avro format)

**Key Options:**

- `--input_format FORMAT` - Input file format: TEXT, JSON, or AVRO
- `--chrome_debug_port PORT` - Connect to Chrome on this port (default: 9222)
- `--max_depth N` - Maximum crawl depth for following links (default: 0)
- `--max_retries N` - Retry failed requests up to N times
- `--sleep_success SECONDS` - Wait time after successful requests
- `--sleep_error SECONDS` - Wait time after errors
- `--load_actions FILE` - Actions to perform after page load
- `--crawl_actions FILE` - Actions to discover and crawl additional links
- `--use_bloom_filter` - Skip duplicate URLs (useful for large crawls)
- `--max_errors N` - Stop after N errors
- `--interactive` - Prompt before each crawl action

**Examples:**

```bash
# Basic crawl
poetry run rubbernecker crawl tmp/urls.txt tmp/output.avro

# Crawl with depth (follow links up to 2 levels)
poetry run rubbernecker crawl tmp/urls.txt tmp/output.avro --max_depth 2

# Crawl with custom actions
poetry run rubbernecker crawl tmp/urls.txt tmp/output.avro \
    --load_actions tmp/load-actions.txt \
    --crawl_actions tmp/crawl-actions.txt

# Crawl with error handling
poetry run rubbernecker crawl tmp/urls.txt tmp/output.avro \
    --max_retries 3 \
    --max_errors 10 \
    --sleep_error 5
```

### `rubbernecker parse`

Extract structured data from crawled HTML using parsers.

**Syntax:**

```bash
rubbernecker parse PARSER_CLASS INPUT_URL OUTPUT_URL
```

**Arguments:**

- `PARSER_CLASS` - Fully qualified parser class name
- `INPUT_URL` - Avro file from crawl command
- `OUTPUT_URL` - Path for parsed output (Avro format)

**Available Parsers:**

- `rubbernecker.parse.standard.StandardPageParser` - Extracts title, headers, links, and body text

**Examples:**

```bash
# Parse with standard parser
poetry run rubbernecker parse rubbernecker.parse.standard.StandardPageParser \
    tmp/raw.avro tmp/parsed.avro

# View parsed results
poetry run avrokit tojson tmp/parsed.avro | jq .
```

### `rubbernecker proxy`

Run a local proxy server to route requests through an upstream proxy.

**Syntax:**

```bash
rubbernecker proxy UPSTREAM [LISTEN]
```

**Arguments:**

- `UPSTREAM` - Upstream proxy (e.g., `username:password@proxy.example.com:8000`)
- `LISTEN` - Local address to listen on (default: `127.0.0.1:3128`)

**Example:**

```bash
# Start proxy server
poetry run rubbernecker proxy "$PROXY_USER:$PROXY_PASS@proxy.example.com:8000" "127.0.0.1:3128"

# Use proxy in Chrome
poetry run rubbernecker chrome --proxy_server "http://127.0.0.1:3128" --headless

# Use proxy in crawl
poetry run rubbernecker crawl tmp/urls.txt tmp/output.avro --chrome_debug_port 9222
```

## Action Scripts

Action scripts define automated interactions with web pages using CSS selectors.

### Action Script Format

```
[url_pattern_regex]
ACTION_NAME selector arguments
ACTION_NAME selector arguments
...
```

### Available Actions

- **SLEEP** `seconds` - Wait for specified duration
- **SCROLL** `pixels` - Scroll page vertically
- **INPUT** `selector text` - Fill form input with text
- **CLICK** `selector` - Click an element
- **CLICK_IF_EXISTS** `selector` - Click if element is present

### Example: Load Actions

Actions to perform after each page loads (use `--load_actions` flag):

```bash
cat > tmp/load-actions.txt << EOF
[news\.ycombinator\.com]
SLEEP 2
SCROLL 500
SLEEP 1
EOF
```

### Example: Crawl Actions

Actions to discover additional URLs during crawling (use `--crawl_actions` flag):

```bash
cat > tmp/crawl-actions.txt << EOF
[news\.ycombinator\.com]
CLICK a.morelink
EOF
```

This will click the "More" link on Hacker News to discover additional pages.

## Advanced Usage

### Full Crawl Example

Complete example crawling Hacker News with actions:

```bash
# Prepare directories
mkdir -p tmp

# Create URL list
cat > tmp/requests.txt << EOF
https://news.ycombinator.com/
EOF

# Create load actions (wait for page to stabilize)
cat > tmp/load-actions.txt << EOF
[news\.ycombinator\.com]
SLEEP 1
SCROLL 500
EOF

# Create crawl actions (discover more pages)
cat > tmp/crawl-actions.txt << EOF
[news\.ycombinator\.com]
CLICK a.morelink
EOF

# Start Chrome
poetry run rubbernecker chrome --headless &

# Crawl with depth 2
poetry run rubbernecker crawl tmp/requests.txt tmp/hn-raw.avro \
    --load_actions tmp/load-actions.txt \
    --crawl_actions tmp/crawl-actions.txt \
    --max_depth 2 \
    --max_retries 2 \
    --sleep_success 1

# Parse results
poetry run rubbernecker parse rubbernecker.parse.standard.StandardPageParser \
    tmp/hn-raw.avro tmp/hn-parsed.avro

# View results
poetry run avrokit tojson tmp/hn-parsed.avro | jq '.title, .links | length'
```

### Using with Proxies

Route traffic through a commercial proxy service:

```bash
# Start local proxy server
poetry run rubbernecker proxy \
    "$PROXY_USER:$PROXY_PASS@residential.proxy.com:8000" \
    "127.0.0.1:3128" &

# Start Chrome through proxy
poetry run rubbernecker chrome \
    --proxy_server "http://127.0.0.1:3128" \
    --chrome_debug_port 9222 \
    --headless &

# Crawl through proxy
poetry run rubbernecker crawl tmp/urls.txt tmp/output.avro \
    --chrome_debug_port 9222
```

## Output Formats

### Crawl Output (Raw HTML)

Avro schema with fields:

- `url` (string) - Crawled URL
- `timestamp` (long) - Unix timestamp in milliseconds
- `body` (string|null) - Raw HTML content
- `error` (string|null) - Error message if request failed
- `metadata` (map|null) - Custom metadata

### Parse Output (StandardPageParser)

Avro schema with fields:

- `url` (string) - Page URL
- `timestamp` (long) - Crawl timestamp
- `title` (string|null) - Page title
- `content_length` (int) - HTML content length
- `body_text` (string|null) - Extracted text content
- `headers` (array|null) - H1-H6 headers with level and text
- `links` (array|null) - Links with text, URL, and external flag

## Troubleshooting

**Chrome connection issues:**

- Ensure Chrome is running with `--chrome_debug_port` matching crawl command
- Check if port 9222 is available: `lsof -i :9222`

**SeleniumBase errors:**

- Update Chrome to the latest version

**Memory issues with large crawls:**

- Use `--use_bloom_filter` to reduce memory for duplicate detection
- Process in smaller batches with multiple crawl commands

## Development

Run tests:

```bash
make test
```

Run all tests (including integration tests):

```bash
make test-all
```

Run tests with coverage:

```bash
make test-coverage
```

Lint and type check:

```bash
make lint
make typecheck
```

Format code:

```bash
make format
```

Build the package:

```bash
make build
```

Clean up build artifacts:

```bash
make clean
```

Run with debug logging:

```bash
poetry run rubbernecker --debug crawl tmp/urls.txt tmp/output.avro
```

## License

Apache-2.0
