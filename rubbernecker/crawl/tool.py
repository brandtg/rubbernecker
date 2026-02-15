# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from urllib.parse import urlparse
from avrokit import (
    URL,
    avro_reader,
    avro_schema,
    avro_writer,
    create_url_mapping,
    parse_url,
)
from datetime import datetime
from enum import Enum
from seleniumbase import SB
from typing import Generator, List
import argparse
import logging
import re
import time
import json
from rubbernecker.crawl.bloomfilter import BloomFilter
from .actions import (
    CrawlActionPlan,
    parse_crawl_action_plans,
    crawl_action,
    CrawlActionName,
)

logger = logging.getLogger(__name__)

SCHEMA = avro_schema(
    {
        "name": "Page",
        "type": "record",
        "fields": [
            {"name": "url", "type": "string"},
            {"name": "timestamp", "type": "long"},
            {"name": "body", "type": ["null", "string"], "default": None},
            {"name": "error", "type": ["null", "string"], "default": None},
            # TODO Support passing metadata from the request
            {
                "name": "metadata",
                "type": [
                    "null",
                    {
                        "type": "map",
                        "values": ["null", "string"],
                    },
                ],
                "default": None,
            },
        ],
    }
)


class InputFormat(Enum):
    TEXT = "text"
    JSON = "json"
    AVRO = "avro"


DEFAULT_INPUT_FORMAT: InputFormat = InputFormat.TEXT
DEFAULT_SLEEP_SUCCESS: int = 3
DEFAULT_SLEEP_ERROR: int = 10
DEFAULT_MAX_DEPTH: int = 0
DEFAULT_MAX_RETRIES: int = 0
DEFAULT_REPORT_INTERVAL: int = 100


@dataclass
class CrawlToolStats:
    count_input: int = 0
    count_output: int = 0
    count_error: int = 0


class CrawlTool:
    def name(self) -> str:
        return "crawl"

    def bloom_filter_key(self, url: str) -> str:
        """
        Generate a key for the Bloom filter based on the URL.

        :param url: The URL to generate a key for.
        :return: The generated key.
        """
        parsed_url = urlparse(url.lower())
        return f"{parsed_url.netloc}:{parsed_url.path}:{parsed_url.query}"

    def is_driver_alive(self, driver) -> bool:
        """
        Check if the Selenium driver is still alive.

        :param driver: The Selenium WebDriver instance.
        :return: True if the driver is alive, False otherwise.
        """
        try:
            driver.current_url
            return True
        except Exception:
            return False

    def restart_browser(self, sb, headless: bool, proxy_server: str | None = None):
        """
        Restart the Selenium browser.

        :param sb: The SeleniumBase instance.
        :param headless: Whether to run in headless mode.
        :param proxy_server: Optional proxy server URL.
        """
        sb.driver.quit()
        sb.__init__(
            uc=True,
            test=True,
            incognito=True,
            headless=headless,
            proxy=proxy_server,
            locale="en-US",
        )

    def load_bloom_filter(self, output_url: URL) -> BloomFilter | None:
        """
        Load a Bloom filter from the output URL.

        :param output_url: URL to the output file.
        :return: A Bloom filter containing the URLs from the output file.
        """
        if output_url.exists():
            count = 0
            bloom_filter = BloomFilter()
            for url in output_url.expand():
                with avro_reader(url.with_mode("rb")) as reader:
                    for record in reader:
                        if (
                            isinstance(record, dict)
                            and "url" in record
                            and record.get("error") is None
                        ):
                            bloom_filter.add(self.bloom_filter_key(record["url"]))
                            count += 1
            if count > 0:
                logger.debug(
                    "Loaded %d URLs into Bloom filter from %s", count, output_url
                )
                return bloom_filter
        return None

    def load_requests(
        self,
        input_url: URL,
        input_format: InputFormat,
        bloom_filter: BloomFilter | None = None,
    ) -> Generator[str, None, None]:
        """
        Load requests from the input URL based on the specified format.

        :param input_url: URL to the input file.
        :param input_format: Format of the input file (text, JSON, or Avro).
        :param bloom_filter: Optional Bloom filter to check for already performed requests.
        :return: A generator yielding URLs from the input file.
        """
        logger.debug(
            "Loading requests from %s with format %s (bloom_filter=%s)",
            input_url,
            input_format,
            bloom_filter,
        )
        if input_format == InputFormat.TEXT:
            # Input is a text file with one URL per line
            with input_url.with_mode("r") as file:
                for line in file:
                    url = line.strip()
                    if isinstance(url, bytes):
                        url = url.decode("utf-8")
                    if not bloom_filter or not bloom_filter.check(
                        self.bloom_filter_key(url)
                    ):
                        yield url
        elif input_format == InputFormat.JSON:
            # Input is a JSONL file with one URL per line
            with input_url.with_mode("r") as file:
                for line in file:
                    data = json.loads(line)
                    url = data["url"]
                    if isinstance(url, bytes):
                        url = url.decode("utf-8")
                    if not bloom_filter or not bloom_filter.check(
                        self.bloom_filter_key(url)
                    ):
                        yield url
        elif input_format == InputFormat.AVRO:
            # Input is an Avro file
            with avro_reader(input_url.with_mode("rb")) as reader:
                for record in reader:
                    if isinstance(record, dict) and "url" in record:
                        url = record["url"]
                        if isinstance(url, bytes):
                            url = url.decode("utf-8")
                        if not bloom_filter or not bloom_filter.check(
                            self.bloom_filter_key(url)
                        ):
                            yield url

    def crawl(
        self,
        base_input_url: URL,
        base_output_url: URL,
        headless: bool = False,
        interactive: bool = False,
        input_format: InputFormat = DEFAULT_INPUT_FORMAT,
        sleep_success: int = DEFAULT_SLEEP_SUCCESS,
        sleep_error: int = DEFAULT_SLEEP_ERROR,
        load_actions: List[CrawlActionPlan] | None = None,
        crawl_actions: CrawlActionPlan | None = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_retries: int = DEFAULT_MAX_RETRIES,
        report_interval: int = DEFAULT_REPORT_INTERVAL,
        use_bloom_filter: bool = False,
        max_errors: int | None = None,
        proxy_server: str | None = None,
    ) -> CrawlToolStats:
        # Load the Bloom filter if needed
        bloom_filter: BloomFilter | None = None
        if use_bloom_filter:
            try:
                bloom_filter = self.load_bloom_filter(base_output_url)
                logger.debug("Loaded Bloom filter: %s", bloom_filter)
            except Exception as e:
                logger.warning("Failed to load Bloom filter: %s", e)

        stats = CrawlToolStats()
        first_request = True

        with SB(
            uc=True,
            test=True,
            incognito=True,
            headless=headless,
            proxy=proxy_server,
            locale="en-US",
        ) as sb:
            # Iterate over the input and output URLs
            for input_url, output_url in create_url_mapping(
                base_input_url, base_output_url
            ):
                logger.info("Mapping %s to %s", input_url, output_url)
                with avro_writer(output_url.with_mode("a+b"), SCHEMA) as writer:
                    # Execute requests
                    for url in self.load_requests(
                        input_url, input_format, bloom_filter=bloom_filter
                    ):
                        # Report progress
                        if (
                            stats.count_input > 0
                            and stats.count_input % report_interval == 0
                        ):
                            logger.info("%s", stats)

                        # Mark the timestamp and depth
                        stats.count_input += 1
                        timestamp = int(datetime.now().timestamp())  # seconds
                        depth = 0
                        retries = 0
                        crawling = False

                        while True:
                            try:
                                # Check if browser is still alive
                                if not self.is_driver_alive(sb.driver):
                                    logger.warning(
                                        "Browser died, restarting for URL: %s", url
                                    )
                                    first_request = True
                                    self.restart_browser(sb, headless, proxy_server)

                                logger.info(
                                    "Crawling URL: %s (depth=%d, retries=%s)",
                                    url,
                                    depth,
                                    retries,
                                )

                                # Navigate to the URL
                                if not crawling:
                                    if first_request:
                                        sb.activate_cdp_mode(url)
                                        first_request = False
                                    elif sb.driver is None:
                                        raise Exception(
                                            "SeleniumBase driver is not initialized"
                                        )
                                    else:
                                        sb.driver.execute_cdp_cmd(
                                            "Page.navigate", {"url": url}
                                        )

                                # Wait for page to be fully loaded before capturing
                                sb.wait_for_ready_state_complete()

                                # Perform load actions if provided
                                if load_actions:
                                    for plan in load_actions:
                                        if plan.should_run(url):
                                            plan_result = plan.run(sb.driver)
                                            if not plan_result:
                                                logger.error(
                                                    "Load actions failed for URL: %s",
                                                    url,
                                                )
                                                break

                                # Wait for the page to load
                                if interactive:
                                    # Pause if in interactive mode
                                    user_input = input(
                                        "Press any key to continue or 'q' to quit: "
                                    )
                                    if user_input.lower() == "q":
                                        logger.info("Exiting interactive mode.")
                                        return stats
                                else:
                                    # Sleep between requests
                                    time.sleep(sleep_success)

                                # Save the crawled data to the output URL
                                current_url = sb.get_current_url()
                                if isinstance(current_url, bytes):
                                    current_url = current_url.decode("utf-8")
                                writer.append(
                                    {
                                        "url": current_url,
                                        "timestamp": timestamp,
                                        "body": sb.get_page_source(),
                                    }
                                )
                                stats.count_output += 1

                                # Check the current depth
                                if depth >= max_depth:
                                    logger.debug(
                                        "Maximum depth reached for URL: %s", url
                                    )
                                    break
                                depth += 1

                                # Run the crawl script to see if we should continue
                                # N.b. the action will be run and we'll expect the page to navigate to
                                # whatever is next. If the action returns False, we should stop the crawl
                                # and continue to the next URL. We should also limit the maximum depth of
                                # the crawl.
                                if crawl_actions and crawl_actions.should_run(url):
                                    # Set the crawling flag to True so we don't reload the page
                                    crawling = True
                                    if not crawl_actions.run(sb.driver):
                                        logger.debug("Crawl finished for URL: %s", url)
                                        break
                                else:
                                    # No crawl actions provided, just break
                                    break
                            except Exception as e:
                                # Check if browser died
                                if not self.is_driver_alive(sb.driver):
                                    logger.warning(
                                        "Browser died during crawl, restarting: %s", e
                                    )
                                    first_request = True
                                    self.restart_browser(sb, headless, proxy_server)
                                    # Retry the same URL
                                    continue

                                # Sleep on error if not in interactive mode
                                if not interactive:
                                    time.sleep(sleep_error)

                                # Log the error and save it to the output URL
                                logger.error("Error crawling URL %s: %s", url, e)
                                writer.append(
                                    {
                                        "url": url,
                                        "timestamp": timestamp,
                                        "error": str(e),
                                    }
                                )
                                stats.count_error += 1

                                # Check if we should exit due to errors
                                if max_errors and stats.count_error >= max_errors:
                                    raise Exception(f"Max errors reached: {max_errors}")

                                # Check if we should retry
                                if retries >= max_retries:
                                    logger.debug(
                                        "Maximum retries reached for URL: %s", url
                                    )
                                    break
        return stats

    def configure(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name(), help="Crawl web pages")
        parser.add_argument(
            "input_url",
            help="URL containing requests to crawl",
        )
        parser.add_argument(
            "output_url",
            help="URL to save the crawled data",
        )
        parser.add_argument(
            "--input_format",
            type=InputFormat,
            choices=list(InputFormat),
            default=DEFAULT_INPUT_FORMAT,
            help="Format of the input URL",
        )
        parser.add_argument(
            "--headless",
            action="store_true",
            help="Run Chrome in headless mode (default: supervised mode with visible browser)",
        )
        parser.add_argument(
            "--interactive",
            action="store_true",
            help="Run in interactive mode",
        )
        parser.add_argument(
            "--sleep_success",
            type=int,
            default=DEFAULT_SLEEP_SUCCESS,
            help="Sleep time after a successful request",
        )
        parser.add_argument(
            "--sleep_error",
            type=int,
            default=DEFAULT_SLEEP_ERROR,
            help="Sleep time after an error",
        )
        parser.add_argument(
            "--load_actions",
            help="Crawl action script to perform after page load",
        )
        parser.add_argument(
            "--sleep_after_load",
            type=float,
            help="Sleep for N seconds after page load (shortcut for creating a load action plan)",
        )
        parser.add_argument(
            "--crawl_actions",
            help="Crawl action script to perform during the crawl",
        )
        parser.add_argument(
            "--max_depth",
            type=int,
            default=DEFAULT_MAX_DEPTH,
            help="Maximum depth to crawl",
        )
        parser.add_argument(
            "--max_retries",
            type=int,
            default=DEFAULT_MAX_RETRIES,
            help="Maximum number of retries on error",
        )
        parser.add_argument(
            "--report_interval",
            type=int,
            default=DEFAULT_REPORT_INTERVAL,
            help="Report progress every N requests",
        )
        parser.add_argument(
            "--use_bloom_filter",
            action="store_true",
            help="Use a Bloom filter on output file to avoid duplicate requests",
        )
        parser.add_argument(
            "--max_errors",
            type=int,
            default=None,
            help="Maximum number of errors before exiting",
        )
        parser.add_argument(
            "--proxy_server",
            help="Proxy server URL (e.g., http://localhost:3128)",
        )

    def parse_load_actions(
        self,
        actionsfile: URL | None,
        sleep_after_load: float | None = None,
    ) -> List[CrawlActionPlan] | None:
        plans: List[CrawlActionPlan] = []
        if sleep_after_load is not None:
            plans.append(
                CrawlActionPlan(
                    url_pattern=re.compile(".*"),
                    actions=[
                        (crawl_action(CrawlActionName.SLEEP), [str(sleep_after_load)])
                    ],
                )
            )
        if actionsfile:
            with actionsfile.with_mode("r") as file:
                script = file.read()
                plans.extend(parse_crawl_action_plans(script))
        return plans if plans else None

    def parse_crawl_actions(self, actionsfile: URL | None) -> CrawlActionPlan | None:
        if actionsfile:
            with actionsfile.with_mode("r") as file:
                script = file.read()
                plans = parse_crawl_action_plans(script)
                if len(plans) != 1:
                    raise ValueError(
                        "Crawl action script must contain exactly one plan"
                    )
                return plans[0]
        return None

    def run(self, args: argparse.Namespace) -> None:
        load_actions_url = parse_url(args.load_actions) if args.load_actions else None
        crawl_actions_url = (
            parse_url(args.crawl_actions) if args.crawl_actions else None
        )
        stats = self.crawl(
            base_input_url=parse_url(args.input_url),
            base_output_url=parse_url(args.output_url),
            headless=args.headless,
            interactive=args.interactive,
            input_format=args.input_format,
            sleep_success=args.sleep_success,
            sleep_error=args.sleep_error,
            load_actions=self.parse_load_actions(
                load_actions_url,
                sleep_after_load=args.sleep_after_load,
            ),
            crawl_actions=self.parse_crawl_actions(crawl_actions_url),
            max_depth=args.max_depth,
            max_retries=args.max_retries,
            report_interval=args.report_interval,
            use_bloom_filter=args.use_bloom_filter,
            max_errors=args.max_errors,
            proxy_server=args.proxy_server,
        )
        logger.info("%s (done)", stats)
