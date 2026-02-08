#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import logging
import argparse
from .base import Tool
from .parse import ParseTool
from .crawl import CrawlTool
from .browser import ProxyTool

TOOLS: list[Tool] = [
    CrawlTool(),
    ParseTool(),
    ProxyTool(),
]


def select_tool(tool_name: str):
    for tool in TOOLS:
        if tool.name() == tool_name:
            return tool
    raise ValueError(f"Tool {tool_name} not found.")


def configure_tools(subparsers: argparse._SubParsersAction) -> None:
    for tool in TOOLS:
        tool.configure(subparsers)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    subparsers = parser.add_subparsers(dest="tool", required=True)
    configure_tools(subparsers)
    args = parser.parse_args()
    logging.basicConfig(
        format="%(levelname)s:%(message)s",
        level=logging.DEBUG if args.debug else logging.INFO,
    )
    try:
        tool = select_tool(args.tool)
        tool.run(args)
    except argparse.ArgumentError as e:
        parser.error(e.message)


if __name__ == "__main__":
    main()
