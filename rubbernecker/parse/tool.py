# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

from .base import Parser, list_parsers
from avrokit import URL, parse_url, create_url_mapping, avro_reader, avro_writer
from dataclasses import dataclass
import argparse
import importlib
import logging

logger = logging.getLogger("parsetool")


@dataclass
class ParseToolStats:
    count_input: int = 0
    count_output: int = 0
    count_error: int = 0


class ParseTool:
    def name(self) -> str:
        return "parse"

    def load_parser(self, class_name: str) -> Parser:
        module_name, _, class_name = class_name.rpartition(".")
        module = importlib.import_module(module_name)
        return getattr(module, class_name)()

    def list_parsers(self) -> list[str]:
        acc: list[str] = []
        for parser in list_parsers():
            acc.append(".".join([parser.__module__, parser.__name__]))
        return acc

    def parse(
        self, parser: Parser, base_input_url: URL, base_output_url: URL
    ) -> ParseToolStats:
        # Stats accumulator
        stats = ParseToolStats()
        # Map the input and output URLs
        for input_url, output_url in create_url_mapping(
            base_input_url, base_output_url
        ):
            logger.info("Parsing %s -> %s", input_url, output_url)
            # Open the input URL and output URL as Avro files
            with (
                avro_reader(input_url.with_mode("rb")) as reader,
                avro_writer(output_url.with_mode("wb"), parser.schema()) as writer,
            ):
                for record in reader:
                    try:
                        stats.count_input += 1
                        for parsed_record in parser.parse(record):
                            if parsed_record is None:
                                logger.debug("Record is None, skipping")
                                continue
                            stats.count_output += 1
                            writer.append(parsed_record)
                    except Exception as e:
                        logger.error("Error parsing record: %s", e)
                        if logging.DEBUG == logger.getEffectiveLevel():
                            logger.exception(e)
                        stats.count_error += 1
                    finally:
                        if logging.DEBUG == logger.getEffectiveLevel():
                            if stats.count_input > 0 and stats.count_input % 100 == 0:
                                logger.debug("%s", stats)
        return stats

    def configure(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name(), help="Parse output of crawl")
        parser.add_argument(
            "name",
            choices=self.list_parsers(),
            help="Name of the parser to use",
        )
        parser.add_argument(
            "input_url",
            help="URL containing result of crawl",
        )
        parser.add_argument(
            "output_url",
            help="URL to save the parsed data",
        )

    def run(self, args: argparse.Namespace) -> None:
        stats = self.parse(
            self.load_parser(args.name),
            parse_url(args.input_url),
            parse_url(args.output_url),
        )
        logger.info("%s (done)", stats)
