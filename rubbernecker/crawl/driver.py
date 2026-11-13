# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

"""
Driver interface shared by the crawl loop.

CrawlTool.crawl consumes drivers through the small CrawlDriver protocol
instead of a concrete class, so alternative drivers (e.g. the best-effort
StealthDriver) can be selected without duplicating the crawl loop.
"""

import logging
from enum import Enum
from typing import Protocol, runtime_checkable

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)

DEFAULT_PAGE_LOAD_TIMEOUT: int = 30


class DriverKind(Enum):
    SELENIUM = "selenium"
    STEALTH = "stealth"


@runtime_checkable
class CrawlDriver(Protocol):
    """
    The driver interface consumed by CrawlTool.crawl.

    Wraps a Selenium Chrome WebDriver with the conveniences the crawl loop
    needs: CDP-based navigation, a ready-state wait, and access to the
    current URL and page source. The raw WebDriver is exposed through
    `driver` for liveness checks and action plans.
    """

    driver: WebDriver

    def quit(self) -> None: ...

    def restart(self) -> None: ...

    def activate_cdp_mode(self, url: str) -> None: ...

    def wait_for_ready_state_complete(
        self, timeout: float = DEFAULT_PAGE_LOAD_TIMEOUT
    ) -> None: ...

    def get_current_url(self) -> str: ...

    def get_page_source(self) -> str: ...

    def __enter__(self) -> "CrawlDriver": ...

    def __exit__(self, exc_type, exc_value, traceback) -> None: ...


class SeleniumDriver:
    """
    Setup/teardown wrapper around a Selenium Chrome WebDriver.

    Provides the small set of browser conveniences used by the crawl loop:
    CDP-based navigation, a ready-state wait, and access to the current URL
    and page source. ChromeDriver is resolved automatically by Selenium
    Manager.

    :param headless: Whether to run Chrome in headless mode.
    :param proxy_server: Optional proxy server URL.
    """

    def __init__(self, headless: bool = False, proxy_server: str | None = None):
        self.headless = headless
        self.proxy_server = proxy_server
        self.driver = self._create_driver()

    def __enter__(self) -> "SeleniumDriver":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.quit()

    def _build_options(self) -> ChromeOptions:
        options = ChromeOptions()
        options.add_argument("--incognito")
        options.add_argument("--lang=en-US")
        if self.headless:
            options.add_argument("--headless=new")
        if self.proxy_server:
            options.add_argument(f"--proxy-server={self.proxy_server}")
        return options

    def _create_driver(self) -> WebDriver:
        return webdriver.Chrome(options=self._build_options())

    def quit(self) -> None:
        """
        Quit the driver, ignoring errors if the browser is already dead.

        :return: None
        """
        if self.driver is None:
            return
        try:
            self.driver.quit()
        except Exception as e:
            logger.debug("Ignoring error while quitting driver: %s", e)
        self.driver = None

    def restart(self) -> None:
        """
        Quit and relaunch the browser with the same configuration.

        :return: None
        """
        self.quit()
        self.driver = self._create_driver()

    def activate_cdp_mode(self, url: str) -> None:
        """
        Navigate to the URL using the Chrome DevTools Protocol.

        :param url: The URL to navigate to.
        :return: None
        """
        assert self.driver is not None, "Driver has been quit"
        self.driver.execute_cdp_cmd("Page.navigate", {"url": url})

    def wait_for_ready_state_complete(
        self, timeout: float = DEFAULT_PAGE_LOAD_TIMEOUT
    ) -> None:
        """
        Wait until the document reaches the "complete" ready state.

        :param timeout: Maximum time to wait, in seconds.
        :return: None
        """
        assert self.driver is not None, "Driver has been quit"
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

    def get_current_url(self) -> str:
        """
        Get the URL of the current page.

        :return: The current URL.
        """
        assert self.driver is not None, "Driver has been quit"
        return self.driver.current_url

    def get_page_source(self) -> str:
        """
        Get the source of the current page.

        :return: The page source.
        """
        assert self.driver is not None, "Driver has been quit"
        return self.driver.page_source
