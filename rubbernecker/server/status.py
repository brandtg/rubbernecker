# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

from rubbernecker.crawl.tool import InputFormat
from rubbernecker.status.tool import StatusTool, StatusToolResult

_EXT_TO_FORMAT = {
    ".txt": InputFormat.TEXT,
    ".jsonl": InputFormat.JSON,
    ".avro": InputFormat.AVRO,
}


def get_status_result(
    input_path: str,
    output_path: str,
    window: int = 100,
) -> StatusToolResult | None:
    """Return a StatusToolResult, or None if the output file is unreadable."""
    import os

    ext = os.path.splitext(input_path)[1].lower()
    input_format = _EXT_TO_FORMAT.get(ext, InputFormat.TEXT)
    tool = StatusTool()
    try:
        return tool.status(
            input_url_strs=[input_path],
            output_url_strs=[output_path],
            input_format=input_format,
            window=window,
        )
    except Exception:
        return None
