# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import re
from unittest.mock import MagicMock

from rubbernecker.crawl.actions import (
    CrawlActionPlan,
    CrawlActionName,
    crawl_action,
    parse_crawl_action_plans,
)


def test_parse_crawl_action_plans():
    # Parse the script into a plan
    script = """
    [news\\.ycombinator\\.com]
    sleep 1
    scroll 100
    input #input python
    click a.morelink
    """
    plans = parse_crawl_action_plans(script)
    assert plans == [
        CrawlActionPlan(
            url_pattern=re.compile(r"news\.ycombinator\.com"),
            actions=[
                (crawl_action(CrawlActionName.SLEEP), ["1"]),
                (crawl_action(CrawlActionName.SCROLL), ["100"]),
                (crawl_action(CrawlActionName.INPUT), ["#input", "python"]),
                (crawl_action(CrawlActionName.CLICK), ["a.morelink"]),
            ],
        )
    ]
    # Check that the plan should run for the given URL
    plan = plans[0]
    assert plan.should_run("https://news.ycombinator.com/")
    # Run the actions on a mock driver
    driver = MagicMock()
    # Sleep
    action, args = plan.actions[0]
    action.run(driver, args)
    # Sleep uses time.sleep, so nothing to verify on driver
    # Scroll
    action, args = plan.actions[1]
    action.run(driver, args)
    driver.execute_script.assert_called_once_with("window.scrollBy(0, 100)")
    # Input
    action, args = plan.actions[2]
    action.run(driver, args)
    driver.type.assert_called_once_with("#input", "python")
    # Click
    action, args = plan.actions[3]
    action.run(driver, args)
    driver.click.assert_called_once_with("a.morelink")
