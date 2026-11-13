# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

"""
Best-effort stealth driver.

Hardens the Selenium Chrome WebDriver against common automation fingerprints:

- launches Chrome with --disable-blink-features=AutomationControlled, which
  keeps navigator.webdriver false,
- points the service at a cached copy of the Selenium-Manager-resolved
  chromedriver binary with its cdc_* variable names neutralized, and
- injects an evasion pack (window.chrome, plugins, languages, permissions,
  WebGL) into every new document via Page.addScriptToEvaluateOnNewDocument.

Navigation and lifecycle management are inherited from SeleniumDriver. This
is best-effort only: determined anti-bot systems also fingerprint TLS,
HTTP/2, IP reputation, and behavior, none of which a browser-side evasion
pack can change. See docs/stealth.md for details and the documented fallback
path.
"""

import json
import logging
from importlib import resources

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.webdriver import WebDriver

from rubbernecker.crawl.chromedriver_patch import get_patched_chromedriver
from rubbernecker.crawl.driver import SeleniumDriver

logger = logging.getLogger(__name__)

# Reported to pages querying WebGL's UNMASKED_VENDOR_WEBGL and
# UNMASKED_RENDERER_WEBGL. Automation contexts often report SwiftShader or an
# empty GPU string instead, which is a strong bot signal.
DEFAULT_WEBGL_VENDOR = "Intel Inc."
DEFAULT_WEBGL_RENDERER = "Intel Iris OpenGL Engine"


def load_evasion_script(
    webgl_vendor: str = DEFAULT_WEBGL_VENDOR,
    webgl_renderer: str = DEFAULT_WEBGL_RENDERER,
) -> str:
    """
    Load the evasion JavaScript pack, filling in the WebGL placeholders.

    :param webgl_vendor: Value reported for UNMASKED_VENDOR_WEBGL.
    :param webgl_renderer: Value reported for UNMASKED_RENDERER_WEBGL.
    :return: The evasion script source.
    """
    script = (
        resources.files("rubbernecker.crawl")
        .joinpath("stealth_evasions.js")
        .read_text(encoding="utf-8")
    )
    return script.replace('"__WEBGL_VENDOR__"', json.dumps(webgl_vendor)).replace(
        '"__WEBGL_RENDERER__"', json.dumps(webgl_renderer)
    )


class StealthDriver(SeleniumDriver):
    """
    SeleniumDriver hardened with best-effort stealth measures.

    Implements the same CrawlDriver interface; only construction and the
    evasion injection differ. See the module docstring for what is masked.

    :param headless: Whether to run Chrome in headless mode.
    :param proxy_server: Optional proxy server URL.
    :param webgl_vendor: WebGL vendor string to report.
    :param webgl_renderer: WebGL renderer string to report.
    """

    def __init__(
        self,
        headless: bool = False,
        proxy_server: str | None = None,
        webgl_vendor: str = DEFAULT_WEBGL_VENDOR,
        webgl_renderer: str = DEFAULT_WEBGL_RENDERER,
    ):
        self.webgl_vendor = webgl_vendor
        self.webgl_renderer = webgl_renderer
        super().__init__(headless=headless, proxy_server=proxy_server)
        self._inject_evasions()

    def _build_options(self) -> ChromeOptions:
        options = super()._build_options()
        options.add_argument("--disable-blink-features=AutomationControlled")
        return options

    def _create_driver(self) -> WebDriver:
        service = ChromeService(executable_path=get_patched_chromedriver())
        return webdriver.Chrome(options=self._build_options(), service=service)

    def restart(self) -> None:
        """
        Quit and relaunch the browser with the same configuration, re-injecting
        the evasion pack into the new session.

        :return: None
        """
        self.quit()
        self.driver = self._create_driver()
        self._inject_evasions()

    def _inject_evasions(self) -> None:
        """
        Inject the evasion pack so it runs before any page script on every
        new document.

        :return: None
        """
        assert self.driver is not None, "Driver has been quit"
        script = load_evasion_script(self.webgl_vendor, self.webgl_renderer)
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument", {"source": script}
        )
