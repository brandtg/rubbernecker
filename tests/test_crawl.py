# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import tempfile
import pytest
import os
from avrokit import parse_url, avro_reader
from rubbernecker.crawl import CrawlTool
from rubbernecker.crawl.tool import InputFormat
from rubbernecker.crawl.actions import parse_crawl_action_plans
from rubbernecker.parse.tool import ParseTool


@pytest.mark.integration
def test_crawl():
    with tempfile.TemporaryDirectory() as tmpdir:
        input_url = parse_url(os.path.join(tmpdir, "requests.txt"))
        output_url = parse_url(os.path.join(tmpdir, "output.avro"))
        # Write some requests to a file
        with input_url.with_mode("w") as f:
            for i in range(5):
                f.write(f"https://news.ycombinator.com/?p={i + 1}\n")
        # Execute the crawl command
        tool = CrawlTool()
        crawl_stats = tool.crawl(
            input_url,
            output_url,
            headless=True,
            input_format=InputFormat.TEXT,
        )
        # Check if the crawl was successful
        assert crawl_stats.count_input == 5
        assert crawl_stats.count_output == 5
        assert crawl_stats.count_error == 0
        # Check if the output file is created
        assert output_url.exists()
        # Read the output file and check if it contains the expected data
        with avro_reader(output_url.with_mode("rb")) as reader:
            count = 0
            for record in reader:
                if isinstance(record, dict):
                    assert record["url"].startswith("https://news.ycombinator.com/?p=")
                    count += 1
            assert count == 5
        # Parse the output file using standard parser
        data_url = parse_url(os.path.join(tmpdir, "parsed_output.avro"))
        parse_tool = ParseTool()
        parse_stats = parse_tool.parse(
            parse_tool.load_parser("rubbernecker.parse.standard.StandardPageParser"),
            output_url,
            data_url,
        )
        assert parse_stats.count_input == 5
        assert parse_stats.count_output == 5
        assert parse_stats.count_error == 0


@pytest.mark.integration
def test_crawl_with_actions():
    with tempfile.TemporaryDirectory() as tmpdir:
        input_url = parse_url(os.path.join(tmpdir, "requests.txt"))
        output_url = parse_url(os.path.join(tmpdir, "output.avro"))
        load_actions_url = parse_url(os.path.join(tmpdir, "load-actions.txt"))
        crawl_actions_url = parse_url(os.path.join(tmpdir, "crawl-actions.txt"))

        # Write some requests to a file
        with input_url.with_mode("w") as f:
            for i in range(1, 6):
                f.write(f"https://news.ycombinator.com/?p={i}\n")

        # Write load actions to a file
        with load_actions_url.with_mode("w") as f:
            f.write("[news\\.ycombinator\\.com]\n")
            f.write("SLEEP 1\n")
            f.write("SCROLL 500\n")

        # Write crawl actions to a file
        with crawl_actions_url.with_mode("w") as f:
            f.write("[news\\.ycombinator\\.com]\n")
            f.write("CLICK a.morelink\n")

        # Parse the action files
        with load_actions_url.with_mode("r") as f:
            load_actions = parse_crawl_action_plans(f.read())
        with crawl_actions_url.with_mode("r") as f:
            crawl_actions = parse_crawl_action_plans(f.read())

        # Execute the crawl command with load_actions, crawl_actions, max_depth, and max_retries
        tool = CrawlTool()
        crawl_stats = tool.crawl(
            input_url,
            output_url,
            headless=True,
            input_format=InputFormat.TEXT,
            load_actions=load_actions,
            crawl_actions=crawl_actions[0] if crawl_actions else None,
            max_depth=2,
            max_retries=2,
        )

        # Check if the crawl was successful
        assert crawl_stats.count_input == 5
        assert crawl_stats.count_output >= 5
        # Allow for occasional network errors in integration tests
        assert crawl_stats.count_error <= 1

        # Check if the output file is created
        assert output_url.exists()

        # Read the output file and check if it contains the expected data
        with avro_reader(output_url.with_mode("rb")) as reader:
            count = 0
            for record in reader:
                if isinstance(record, dict):
                    assert record["url"].startswith("https://news.ycombinator.com/")
                    count += 1
            assert count >= 5

        # Parse the output file using standard parser
        data_url = parse_url(os.path.join(tmpdir, "parsed_output.avro"))
        parse_tool = ParseTool()
        parse_stats = parse_tool.parse(
            parse_tool.load_parser("rubbernecker.parse.standard.StandardPageParser"),
            output_url,
            data_url,
        )
        assert parse_stats.count_input >= 5
        assert parse_stats.count_output >= 5
        assert parse_stats.count_error == 0
