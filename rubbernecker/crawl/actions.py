# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Protocol, Tuple
import logging
import re
import time

logger = logging.getLogger(__name__)


class CrawlActionName(Enum):
    SLEEP = "SLEEP"
    INPUT = "INPUT"
    SCROLL = "SCROLL"
    CLICK = "CLICK"
    CLICK_IF_EXISTS = "CLICK_IF_EXISTS"


# Type alias for SeleniumBase Driver
CrawlDriver = Any


class CrawlAction(Protocol):
    def name(self) -> CrawlActionName: ...
    def run(self, driver: CrawlDriver, args: List[str]) -> bool: ...


class SleepCrawlAction:
    def name(self) -> CrawlActionName:
        return CrawlActionName.SLEEP

    def run(self, driver: CrawlDriver, args: List[str]) -> bool:
        if len(args) != 1:
            raise ValueError(
                "Sleep action requires exactly one argument: duration (seconds)"
            )
        try:
            duration = float(args[0])
            time.sleep(duration)
            return True
        except Exception as e:
            print(f"Error sleeping: {e}")
            return False


class InputCrawlAction:
    def name(self) -> CrawlActionName:
        return CrawlActionName.INPUT

    def run(self, driver: CrawlDriver, args: List[str]) -> bool:
        if len(args) < 2:
            raise ValueError(
                "Input action requires at least two arguments: selector value [value...]"
            )
        try:
            selector = args[0]
            value = " ".join(args[1:])
            driver.type(selector, value)
            return True
        except Exception as e:
            print(f"Error filling input: {e}")
            return False


class ScrollCrawlAction:
    def name(self) -> CrawlActionName:
        return CrawlActionName.SCROLL

    def run(self, driver: CrawlDriver, args: List[str]) -> bool:
        if len(args) != 1:
            raise ValueError("Scroll action requires exactly one argument: amount")
        try:
            amount = int(args[0])
            driver.execute_script(f"window.scrollBy(0, {amount})")
            return True
        except Exception as e:
            print(f"Error scrolling: {e}")
            return False


class ClickCrawlAction:
    def name(self) -> CrawlActionName:
        return CrawlActionName.CLICK

    def run(self, driver: CrawlDriver, args: List[str]) -> bool:
        if len(args) == 0:
            raise ValueError("Click action requires selector")
        try:
            selector = " ".join(args)
            logger.debug(f"Clicking on selector: {selector}")
            driver.click(selector)
            return True
        except Exception as e:
            logger.error(f"Error clicking: {e}")
            return False


class ClickIfExistsCrawlAction:
    def name(self) -> CrawlActionName:
        return CrawlActionName.CLICK_IF_EXISTS

    def run(self, driver: CrawlDriver, args: List[str]) -> bool:
        if len(args) == 0:
            raise ValueError("Click action requires selector")
        try:
            selector = " ".join(args)
            if not driver.is_element_present(selector):
                logger.debug(f"Selector not found: {selector}")
                return True
            logger.debug(f"Clicking on selector: {selector}")
            driver.click(selector)
            return True
        except Exception as e:
            logger.error(f"Error clicking: {e}")
            return False


ACTIONS: List[CrawlAction] = [
    SleepCrawlAction(),
    InputCrawlAction(),
    ScrollCrawlAction(),
    ClickCrawlAction(),
    ClickIfExistsCrawlAction(),
]

ACTION_NAMES: Dict[CrawlActionName, CrawlAction] = {
    action.name(): action for action in ACTIONS
}


def crawl_action(action_name: CrawlActionName) -> CrawlAction:
    """
    Get the crawl action by name.
    """
    action = ACTION_NAMES.get(action_name)
    if action is None:
        raise ValueError(f"Unknown action: {action_name}")
    return action


@dataclass
class CrawlActionPlan:
    url_pattern: re.Pattern
    actions: List[Tuple[CrawlAction, List[str]]]

    def should_run(self, url: str) -> bool:
        """
        Check if the action plan should run for the given URL.
        """
        return self.url_pattern.search(url) is not None

    def run(self, driver: CrawlDriver) -> bool:
        """
        Run the actions on the given driver.

        :param driver: The SeleniumBase driver to run the actions on.
        :return: True if the actions were run successfully, False otherwise.
        """
        for action, args in self.actions:
            if not action.run(driver, args):
                return False
        return True


def parse_crawl_action_plans(script: str) -> List[CrawlActionPlan]:
    """
    Parse a string of crawl actions into a dictionary of action names and their arguments.
    """
    acc: List[CrawlActionPlan] = []
    cur: CrawlActionPlan | None = None
    for line in script.strip().splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            if cur is not None:
                acc.append(cur)
            cur = CrawlActionPlan(
                url_pattern=re.compile(line[1:-1]),
                actions=[],
            )
        elif cur is not None:
            parts = line.split()
            action_name = CrawlActionName(parts[0].upper())
            action_args = parts[1:]
            action = ACTION_NAMES.get(action_name)
            if action is None:
                raise ValueError(f"Unknown action: {action_name}")
            cur.actions.append((action, action_args))
    if cur is not None:
        acc.append(cur)
    return acc
