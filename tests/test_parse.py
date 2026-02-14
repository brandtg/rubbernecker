# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import tempfile
from pathlib import Path

from avrokit import avro_schema, avro_records, avro_writer, parse_url
from rubbernecker.parse.tool import ParseTool


SIMPLE_PARSER = """
from typing import Generator
from avrokit import avro_schema
from avro.schema import Schema
from rubbernecker.parse.base import Parser


class SimpleParser(Parser):
    def schema(self) -> Schema:
        return avro_schema({
            "name": "Simple",
            "type": "record",
            "fields": [
                {"name": "value", "type": "string"}
            ]
        })

    def parse(self, record: object) -> Generator[object | None, None, None]:
        yield {"value": "test"}
"""


def test_load_parser_from_script_path() -> None:
    """Test loading a parser from an arbitrary Python file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SIMPLE_PARSER)
        script_path = f.name

    try:
        tool = ParseTool()
        parser = tool.load_parser("SimpleParser", script_path=script_path)

        assert parser is not None
        assert parser.schema() is not None

        records = list(parser.parse({"url": "http://example.com"}))
        assert len(records) == 1
        assert records[0] == {"value": "test"}
    finally:
        Path(script_path).unlink()


INPUT_SCHEMA = avro_schema(
    {
        "name": "Page",
        "type": "record",
        "fields": [
            {"name": "url", "type": "string"},
            {"name": "timestamp", "type": "long"},
            {"name": "body", "type": ["null", "string"], "default": None},
        ],
    }
)


def test_parse_with_builtin_parser() -> None:
    """Test parsing with the built-in StandardPageParser."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_url = parse_url(tmpdir + "/input.avro")
        output_url = parse_url(tmpdir + "/output.avro")

        test_records = [
            {
                "url": "https://example.com",
                "timestamp": 1234567890,
                "body": '<html><head><title>Test</title></head><body><h1>Hello</h1><a href="/link">Link</a></body></html>',
            },
            {
                "url": "https://example.com/page2",
                "timestamp": 1234567891,
                "body": "<html><head><title>Page 2</title></head><body><h2>World</h2></body></html>",
            },
        ]

        with avro_writer(input_url.with_mode("wb"), INPUT_SCHEMA) as writer:
            for record in test_records:
                writer.append(record)

        tool = ParseTool()
        parser = tool.load_parser("rubbernecker.parse.standard.StandardPageParser")
        stats = tool.parse(parser, input_url, output_url)

        assert stats.count_input == 2
        assert stats.count_output == 2
        assert stats.count_error == 0
        assert output_url.exists()

        results = list(avro_records(output_url.with_mode("rb")))
        assert len(results) == 2
        assert results[0]["url"] == "https://example.com"
        assert results[0]["title"] == "Test"
        assert "Hello" in results[0]["body_text"]
        assert len(results[0]["headers"]) == 1
        assert results[0]["headers"][0]["level"] == 1
        assert results[0]["headers"][0]["text"] == "Hello"
        assert len(results[0]["links"]) == 1
