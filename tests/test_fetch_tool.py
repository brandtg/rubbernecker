# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile
import pytest
from avrokit import parse_url
from rubbernecker.fetch import FetchTool


@pytest.mark.integration
def test_fetch_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        input_url = parse_url(os.path.join(tmpdir, "urls.txt"))
        output_url = parse_url(os.path.join(tmpdir, "output"))

        with input_url.with_mode("w") as f:
            f.write("https://httpbin.org/image/png\n")

        tool = FetchTool()
        stats = tool.fetch(input_url, output_url, parallelism=1)

        assert stats.count_input == 1
        assert stats.count_output == 1
        assert stats.count_error == 0

        image_path = os.path.join(tmpdir, "output", "image", "png")
        assert os.path.exists(image_path)

        with open(image_path, "rb") as f:
            content = f.read()
        assert len(content) > 0
        assert content[:4] == b"\x89PNG"


@pytest.mark.integration
def test_fetch_tool_parallel():
    with tempfile.TemporaryDirectory() as tmpdir:
        input_url = parse_url(os.path.join(tmpdir, "urls.txt"))
        output_url = parse_url(os.path.join(tmpdir, "output"))

        with input_url.with_mode("w") as f:
            f.write("https://httpbin.org/image/png\n")
            f.write("https://httpbin.org/json\n")

        tool = FetchTool()
        stats = tool.fetch(input_url, output_url, parallelism=2)

        assert stats.count_input == 2
        assert stats.count_output == 2
        assert stats.count_error == 0

        png_path = os.path.join(tmpdir, "output", "image", "png")
        json_path = os.path.join(tmpdir, "output", "json")

        assert os.path.exists(png_path)
        assert os.path.exists(json_path)

        with open(png_path, "rb") as f:
            assert f.read()[:4] == b"\x89PNG"

        with open(json_path, "r") as f:
            content = f.read()
        assert '"slideshow"' in content
