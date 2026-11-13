<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# In-repo stealth driver

## 0. Title

Implement best-effort stealth crawling in-repo behind a shared driver interface

## 1. Problem

Stealth was an original requirement: rubbernecker ≤ 0.0.8 used seleniumbase's
`SB(uc=True, ...)` context manager (rubbernecker/crawl/tool.py), whose UC mode
patched chromedriver and masked automation fingerprints (navigator.webdriver,
chromedriver's internal `cdc_*` variable names, CDP runtime leaks), plus
CDP-mode navigation (`activate_cdp_mode`) that avoids webdriver-detectable page
loads. The seleniumbase-removal work replaced this with a plain-selenium
`SeleniumDriver` wrapper (same file): vanilla chromedriver resolved by Selenium
Manager, `--incognito/--lang/--headless/--proxy-server` options, CDP
`Page.navigate`, and a `WebDriverWait` ready-state poll. CDP navigation alone
is not equivalent — the browser itself is still fingerprintable.

Two structural facts shape the fix:

- The base-install footprint win is real and worth keeping. seleniumbase pulls
  ~55 transitive packages (the pytest toolchain, behave, a GUI/X11 automation
  stack with sdist-only builds); the current runtime resolves to ~30.
- `SeleniumDriver` is a concrete class with no seam for an alternative driver,
  and `CrawlTool.crawl` consumes it directly (`driver.driver`,
  `activate_cdp_mode`, `wait_for_ready_state_complete`, `restart`). Any stealth
  driver needs that seam first.

What UC mode actually does decomposes into four pieces, three of which are
small and one of which we already have:

1. Mask `navigator.webdriver` — one Chrome flag:
   `--disable-blink-features=AutomationControlled`
2. Neutralize chromedriver's `cdc_*` variables that sites scan for — a ~100
   line binary patcher: Selenium Manager already downloads chromedriver, we
   byte-replace the fixed-length `cdc_` strings with same-length garbage into
   a cached copy, and point the service at the patched binary
3. JS environment evasions (window.chrome object, plugins/languages,
   permissions query, WebGL vendor) — ~10 well-known snippets injected once per
   session via `Page.addScriptToEvaluateOnNewDocument`, which the wrapper
   already speaks
4. CDP-based navigation — already implemented in the refactor

The obvious off-the-shelf replacement, undetected-chromedriver, is stale: last
PyPI release 3.5.5 (sdist-only, February 2024), repo last pushed July 2025
with ~1.1k open issues. Its evasion pack is no more current than one we would
maintain ourselves, it is GPL-3.0 (rubbernecker is Apache-2.0), and it predates
Selenium Manager and standard CDP navigation. nodriver, the same author's
successor, is actively maintained but is asyncio-only with no selenium — a
different execution model and the largest integration lift.

## 2. Impact

Consumers crawling bot-protected targets (Cloudflare/Imperva-class) get
challenged or blocked: crawl errors, empty page bodies, `count_error` spikes.
It fails quietly — errors are written into the Avro output and the tool still
exits 0 unless `--max_errors` trips — so users may not notice until data
quality rots. Integration tests do not catch this: news.ycombinator.com does
not bot-check, so they verify plumbing, not stealth. A homemade evasion layer
is an arms race and will lag determined detectors; the goal is best-effort
stealth with a documented fallback path, not a guarantee.

## 3. Potential solutions

- In-repo stealth driver (preferred): factor `SeleniumDriver` into a small
  driver interface shared by the crawl loop, and add a stealth implementation
  that (a) passes the AutomationControlled flag, (b) patches the
  Selenium-Manager-resolved chromedriver binary to neutralize `cdc_*`
  variables into a cached copy, and (c) injects an evasion pack ported from
  MIT-licensed sources (puppeteer-extra-plugin-stealth / selenium-stealth)
  via `Page.addScriptToEvaluateOnNewDocument`, reusing the existing CDP
  navigation. Zero new runtime dependencies; ~300 lines, all inspectable
  in-repo. Tradeoffs: we own the arms race; attribution required; two driver
  implementations to keep aligned to the interface.
- rubbernecker[undetected] extra with an `UndetectedDriver` using
  undetected-chromedriver (`uc.Chrome` → same interface): fallback if the
  in-repo layer is bypassed by a real target. uc's dep tree is small
  (selenium, requests, websockets, packaging), so the extra stays lean.
  Tradeoffs: stale upstream (needs a spike first), GPL-3.0 license, second
  implementation to maintain.
- rubbernecker[seleniumbase] extra with a `SeleniumBaseDriver` implementation:
  reuse SB's actively maintained UC/CDP modes. Tradeoffs: heavy opt-in install
  (~55 packages), second implementation to maintain, but zero novelty risk.
- nodriver: actively maintained (October 2026) and tiny (mss, websockets,
  deprecated), but asyncio-only and selenium-free — biggest integration lift
  into the synchronous crawl loop.
- Do nothing: document that stealth was dropped in the seleniumbase-removal
  release. Zero effort; protected targets keep failing.

## 4. Acceptance criteria

1. A spike proves the pieces against current Chrome (headless and visible):
   the AutomationControlled flag removes `navigator.webdriver`; the patched
   chromedriver launches and no `cdc_` string is greppable in the patched
   binary; the evasion JS evaluates correctly on a fresh document.
2. Base install footprint is unchanged — zero new runtime dependencies in
   `pip install rubbernecker`'s resolution.
3. Driver selection is exposed on `CrawlTool.crawl` and the CLI (e.g.
   `--driver stealth`), with plain selenium as the default so existing
   behavior is untouched.
4. Both drivers implement one shared interface and the crawl loop is not
   duplicated; unit tests cover the patcher (fixture binary string), evasion
   injection, and selection; an integration test covers a stealth crawl end
   to end.
5. The evasion pack is MIT-ported with an attribution file; no GPL code enters
   the repository.
6. README and QUICKSTART document the stealth driver, its best-effort nature,
   and the fallback path (undetected extra) if a target still blocks.
