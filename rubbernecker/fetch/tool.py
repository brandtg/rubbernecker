# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.parse import urlparse
from avrokit import URL, parse_url
from rubbernecker.crawl.bloomfilter import BloomFilter

logger = logging.getLogger("fetchtool")


@dataclass
class FetchToolStats:
    count_input: int = 0
    count_output: int = 0
    count_error: int = 0
    count_skipped: int = 0


class FetchTool:
    def name(self) -> str:
        return "fetch"

    def configure(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name(), help="Fetch assets from URLs")
        parser.add_argument(
            "input_url",
            help="URL to the text file containing URLs to fetch",
        )
        parser.add_argument(
            "output_url",
            help="URL to the output directory",
        )
        parser.add_argument(
            "--parallelism",
            type=int,
            default=1,
            help="Number of concurrent fetches (default: 1)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Redownload even if file already exists (default: skip existing)",
        )

    def load_bloom_filter(self, output_url: URL) -> BloomFilter | None:
        if output_url.exists():
            bloom_filter = BloomFilter()
            count = 0
            base_path = output_url.url.rstrip("/") + "/"
            for url in output_url.expand():
                if url.url.startswith(base_path):
                    path = url.url[len(base_path) :]
                else:
                    parsed = urlparse(url.url)
                    path = parsed.path.lstrip("/")
                if path:
                    bloom_filter.add(path)
                    count += 1
            if count > 0:
                logger.debug(
                    "Loaded %d paths into Bloom filter from %s", count, output_url
                )
                return bloom_filter
        return None

    def fetch_url(
        self,
        url: str,
        output_base_url: URL,
        force: bool,
        bloom_filter: BloomFilter | None,
    ) -> tuple[bool, bool]:
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            content = response.content

            parsed = urlparse(url)
            path = parsed.path.lstrip("/")

            if not path:
                logger.warning("URL %s has no path, skipping", url)
                return False, False

            if not force and bloom_filter and bloom_filter.check(path):
                logger.debug("File already exists (bloom filter), skipping: %s", path)
                return True, True

            output_url = parse_url(output_base_url.url + "/" + path)
            with output_url.with_mode("wb") as f:
                f.write(content)

            if bloom_filter:
                bloom_filter.add(path)

            logger.debug("Fetched %s -> %s", url, output_url)
            return True, False

        except Exception as e:
            logger.error("Error fetching %s: %s", url, e)
            return False, False

    def fetch(
        self, input_url: URL, output_url: URL, parallelism: int, force: bool = False
    ) -> FetchToolStats:
        stats = FetchToolStats()

        bloom_filter: BloomFilter | None = None
        if not force:
            try:
                bloom_filter = self.load_bloom_filter(output_url)
            except Exception as e:
                logger.warning("Failed to load bloom filter: %s", e)

        with input_url.with_mode("r") as f:
            urls = [line.strip() for line in f if line.strip()]

        logger.info("Fetching %d URLs with parallelism=%d", len(urls), parallelism)

        if bloom_filter:
            logger.info("Bloom filter loaded, will skip existing files")

        with ThreadPoolExecutor(max_workers=parallelism) as executor:
            futures = {
                executor.submit(
                    self.fetch_url, url, output_url, force, bloom_filter
                ): url
                for url in urls
            }

            for future in as_completed(futures):
                url = futures[future]
                stats.count_input += 1
                try:
                    success, skipped = future.result()
                    if success:
                        if skipped:
                            stats.count_skipped += 1
                        else:
                            stats.count_output += 1
                    else:
                        stats.count_error += 1
                except Exception as e:
                    logger.error("Error processing %s: %s", url, e)
                    stats.count_error += 1

                if logging.DEBUG != logger.getEffectiveLevel():
                    if stats.count_output > 0 and stats.count_output % 100 == 0:
                        logger.info("%s", stats)

        return stats

    def run(self, args: argparse.Namespace) -> None:
        stats = self.fetch(
            parse_url(args.input_url),
            parse_url(args.output_url),
            args.parallelism,
            args.force,
        )
        logger.info("%s (done)", stats)
