# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from collections.abc import Generator
from typing import Any, cast
from urllib.parse import urlparse

from avro.schema import Schema
from avrokit import avro_schema
from bs4 import BeautifulSoup, Tag

from .base import Parser

logger = logging.getLogger(__name__)


class StandardPageParser(Parser):
    def schema(self) -> Schema:
        return avro_schema(
            {
                "name": "StandardPage",
                "type": "record",
                "fields": [
                    {"name": "url", "type": "string"},
                    {"name": "timestamp", "type": "long"},
                    {"name": "content_length", "type": "int"},
                    {"name": "title", "type": ["null", "string"], "default": None},
                    {"name": "body_text", "type": ["null", "string"], "default": None},
                    {
                        "name": "headers",
                        "type": [
                            "null",
                            {
                                "type": "array",
                                "items": {
                                    "type": "record",
                                    "name": "Header",
                                    "fields": [
                                        {"name": "level", "type": "int"},
                                        {
                                            "name": "text",
                                            "type": ["null", "string"],
                                            "default": None,
                                        },
                                    ],
                                },
                            },
                        ],
                        "default": None,
                    },
                    {
                        "name": "links",
                        "type": [
                            "null",
                            {
                                "type": "array",
                                "items": {
                                    "type": "record",
                                    "name": "Link",
                                    "fields": [
                                        {
                                            "name": "text",
                                            "type": ["null", "string"],
                                            "default": None,
                                        },
                                        {
                                            "name": "url",
                                            "type": ["null", "string"],
                                            "default": None,
                                        },
                                        {
                                            "name": "external",
                                            "type": "boolean",
                                            "default": False,
                                        },
                                    ],
                                },
                            },
                        ],
                    },
                ],
            }
        )

    def _parse_headers(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        headers: list[dict[str, Any]] = []
        for header in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            if isinstance(header, Tag):
                level = int(header.name[1])
                headers.append({"level": level, "text": header.get_text()})
        return headers

    def _parse_links(self, url: str, soup: BeautifulSoup) -> list[dict[str, Any]]:
        parsed_url = urlparse(url)
        links: list[dict[str, Any]] = []
        for link in soup.find_all("a"):
            if isinstance(link, Tag):
                href = link.get("href")
                if href:
                    parsed_href = urlparse(str(href))
                    links.append(
                        {
                            "text": link.get_text(),
                            "url": str(href),
                            "external": bool(parsed_href.netloc)
                            and (parsed_href.netloc != parsed_url.netloc),
                        }
                    )
        return links

    def parse(self, record: object) -> Generator[object | None, None, None]:
        if not isinstance(record, dict):
            logger.error("Record is not a dictionary: %s", record)
            return
        r = cast(dict[str, Any], record)
        soup = BeautifulSoup(r["body"], "html.parser")
        body_text = soup.body.get_text() if soup.body else None
        yield {
            "url": r["url"],
            "timestamp": r["timestamp"],
            "title": soup.title.get_text() if soup.title else None,
            "content_length": len(r["body"]) if r["body"] else 0,
            "body_text": body_text,
            "headers": self._parse_headers(soup),
            "links": self._parse_links(r["url"], soup),
        }
