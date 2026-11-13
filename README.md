<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# Rubbernecker

A web scraping engine built with Python and Selenium that crawls web pages,
stores raw HTML, and parses structured data. Supports configurable page actions
and depth-based crawling.

## Installation

### Prerequisites

**Python 3.12+**

**Google Chrome**

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

```bash
make install
```

Or manually:

```bash
uv sync
```

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for a step-by-step tutorial.

## Stealth Crawling

Targets with bot protection (Cloudflare/Imperva-class) can be crawled with
`--driver stealth`, which masks common automation fingerprints
(`navigator.webdriver`, chromedriver's `cdc_*` variables, and a JavaScript
evasion pack). This is best-effort only — see
[docs/stealth.md](docs/stealth.md) for what it does, its limits, and the
fallback path if a target still blocks you.

```bash
uv run rubbernecker crawl tmp/urls.txt tmp/output.avro --driver stealth
```

## Commands

| Command | Description |
|---|---|
| [`crawl`](docs/commands/crawl.md) | Scrape websites and save raw HTML to Avro files |
| [`fetch`](docs/commands/fetch.md) | Download assets from a list of URLs |
| [`parse`](docs/commands/parse.md) | Extract structured data from crawled HTML |
| [`sitemap`](docs/commands/sitemap.md) | Discover page URLs from sitemaps or robots.txt |

## Documentation

- [Action Scripts](docs/actions.md) — Automate page interactions during crawls
- [Stealth Crawling](docs/stealth.md) — Best-effort evasion of bot detection
- [Output Formats](docs/output-formats.md) — Avro schemas for all command outputs
- [Development](docs/development.md) — Testing, linting, and build commands

## License

Apache-2.0
