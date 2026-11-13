<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# Stealth crawling

Rubbernecker ships two crawl drivers behind a shared interface:

- `selenium` (default) — plain Selenium Chrome, exactly as before
- `stealth` — best-effort evasion of common automation fingerprints

## Usage

```bash
uv run rubbernecker crawl tmp/urls.txt tmp/output.avro --driver stealth
```

Or in Python:

```python
from rubbernecker.crawl.driver import DriverKind
from rubbernecker.crawl.tool import CrawlTool

tool = CrawlTool()
stats = tool.crawl(
    input_url,
    output_url,
    headless=True,
    driver=DriverKind.STEALTH,
)
```

## What it does

The stealth driver is the plain Selenium driver plus three measures:

1. Chrome is launched with `--disable-blink-features=AutomationControlled`,
   which keeps `navigator.webdriver` false.
2. The chromedriver binary resolved by Selenium Manager is copied to a cache
   and patched: its fixed `cdc_*` variable names (which bot detectors scan
   for on `window` and `document`) are replaced with same-length garbage. The
   patch preserves all byte lengths and maps each identifier to a single
   consistent replacement, so the driver keeps working. Patched copies are
   cached under the per-user cache directory (e.g. `~/.cache/rubbernecker/`)
   keyed by the source binary's digest, and re-signing is handled on macOS.
3. An evasion pack (window.chrome object, PDF viewer plugins and mimeTypes,
   navigator.languages, the permissions query, WebGL vendor/renderer) is
   injected into every new document via CDP
   (`Page.addScriptToEvaluateOnNewDocument`), so it runs in the main world
   before any page script. Navigation itself is the same CDP-based
   `Page.navigate` the default driver uses.

## Best-effort, not a guarantee

This is an arms race, and a browser-side evasion pack cannot change TLS
fingerprints, HTTP/2 settings, IP reputation, or behavioral signals.
Determined anti-bot systems (Cloudflare/Imperva-class) may still block you.
The goal is to pass common checks, not all of them.

If a target still blocks the stealth driver, the documented fallback path is
undetected-chromedriver's UC mode — but note it is GPL-3.0, its last PyPI
release is 3.5.5 (sdist-only, 2024), and it predates Selenium Manager, so
treat it as a spike rather than a drop-in: a small custom driver can wrap
`uc.Chrome` behind the same `CrawlDriver` interface
(`rubbernecker/crawl/driver.py`) and be passed through
`rubbernecker.crawl.tool.create_driver`'s registry. A `rubbernecker[undetected]`
extra may be added if the need is real.

## Degraded mode

If the chromedriver patch fails (for example an unsupported binary format),
the stealth driver logs a warning and continues with the unpatched binary:
stealth is degraded, but crawling still works.

## Attribution and licensing

The evasion pack is adapted from MIT-licensed sources
(puppeteer-extra-plugin-stealth, selenium-stealth) and is MIT-licensed; see
[rubbernecker/crawl/ATTRIBUTION.md](https://github.com/brandtg/rubbernecker/blob/main/rubbernecker/crawl/ATTRIBUTION.md)
and [LICENSES/MIT.txt](https://github.com/brandtg/rubbernecker/blob/main/LICENSES/MIT.txt).
No GPL-licensed code is used.
