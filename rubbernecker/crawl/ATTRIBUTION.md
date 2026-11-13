# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

# Third-party attributions

The browser evasion pack shipped in `rubbernecker/crawl/stealth_evasions.js`
is adapted from MIT-licensed sources:

- puppeteer-extra-plugin-stealth — Copyright © 2018 - 2023, berstend and
  contributors. https://github.com/berstend/puppeteer-extra
  (packages/puppeteer-extra-plugin-stealth)
- selenium-stealth — Copyright © 2020, diprajpatra.
  https://github.com/diprajpatra/selenium-stealth

Both are released under the MIT License; the license text is in
LICENSES/MIT.txt. The snippets were ported to a single
`Page.addScriptToEvaluateOnNewDocument` payload and adapted for current
Chrome. No GPL-licensed code (e.g. undetected-chromedriver) is used.

The chromedriver binary patcher (`rubbernecker/crawl/chromedriver_patch.py`)
reimplements the well-known, widely documented technique of replacing
chromedriver's fixed-length `cdc_*` variable names with same-length garbage;
it contains no code from any of the projects above.
