# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import logging
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from avrokit import parse_url
from avrokit.io.reader import PartitionedAvroReader
from avrokit.tools.count import CountTool
from avrokit.url import URL, flatten_urls

from rubbernecker.crawl.tool import InputFormat

logger = logging.getLogger(__name__)

DEFAULT_WINDOW: int = 100


@dataclass
class StatusToolResult:
    # Input stats
    count_input: int = 0
    count_input_duplicates: int = 0  # only populated for text/json formats

    # Output stats
    count_processed: int = 0
    count_success: int = 0
    count_error: int = 0

    # Timestamps (Unix seconds)
    first_timestamp: int | None = None
    last_timestamp: int | None = None

    # Rolling window timestamps for recent rate calculation
    # Stored as a list of the last N timestamps (populated during scan)
    window_timestamps: list[int] = field(default_factory=list)

    @property
    def count_remaining(self) -> int:
        return max(0, self.count_input - self.count_processed)

    @property
    def error_rate(self) -> float | None:
        if self.count_processed == 0:
            return None
        return self.count_error / self.count_processed

    @property
    def overall_rate(self) -> float | None:
        """Pages per second over the full crawl duration."""
        if (
            self.first_timestamp is None
            or self.last_timestamp is None
            or self.last_timestamp == self.first_timestamp
            or self.count_processed < 2
        ):
            return None
        elapsed = self.last_timestamp - self.first_timestamp
        return self.count_processed / elapsed

    @property
    def recent_rate(self) -> float | None:
        """Pages per second over the most recent window of records."""
        if len(self.window_timestamps) < 2:
            return None
        elapsed = self.window_timestamps[-1] - self.window_timestamps[0]
        if elapsed == 0:
            return None
        return (len(self.window_timestamps) - 1) / elapsed

    def _format_eta(self, rate: float | None) -> str:
        if rate is None or rate <= 0 or self.count_remaining == 0:
            return "N/A"
        seconds = int(self.count_remaining / rate)
        return str(timedelta(seconds=seconds))

    @property
    def eta_overall(self) -> str:
        return self._format_eta(self.overall_rate)

    @property
    def eta_recent(self) -> str:
        return self._format_eta(self.recent_rate)

    def _format_rate(self, rate: float | None) -> str:
        if rate is None:
            return "N/A"
        per_hour = rate * 3600
        return f"{rate:.2f} pages/sec  ({per_hour:,.0f}/hr)"

    def _format_ts(self, ts: int | None) -> str:
        if ts is None:
            return "N/A"
        return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    def to_text(
        self,
        input_urls: list[str],
        output_urls: list[str],
        window: int,
    ) -> str:
        pct = (
            f"{self.count_processed / self.count_input * 100:.1f}%"
            if self.count_input > 0
            else "N/A"
        )
        error_rate_str = (
            f"{self.error_rate * 100:.1f}% error rate"
            if self.error_rate is not None
            else "N/A"
        )
        dup_line = ""
        if self.count_input_duplicates > 0:
            dup_line = (
                f"  Duplicates:    {self.count_input_duplicates:>12,}"
                "  (re-crawled unless bloom filter is active)\n"
            )

        lines = [
            "Crawl Status",
            "============",
            f"Input:   {', '.join(input_urls)}",
            f"Output:  {', '.join(output_urls)}",
            "",
            "Progress",
            "--------",
            f"Total URLs:      {self.count_input:>12,}",
        ]
        if dup_line:
            lines.append(dup_line.rstrip())
        lines += [
            f"Processed:       {self.count_processed:>12,}  ({pct})",
            f"  Successes:     {self.count_success:>12,}",
            f"  Errors:        {self.count_error:>12,}  ({error_rate_str})",
            f"Remaining:       {self.count_remaining:>12,}",
            "",
            "Timing",
            "------",
            f"Started at:      {self._format_ts(self.first_timestamp)}",
            f"Last record:     {self._format_ts(self.last_timestamp)}",
            "",
            f"Overall rate:    {self._format_rate(self.overall_rate)}",
            f"Recent rate:     {self._format_rate(self.recent_rate)}  [last {window} records]",
            "",
            f"ETA (overall):   {self.eta_overall}",
            f"ETA (recent):    {self.eta_recent}",
        ]
        return "\n".join(lines)

    def to_json_dict(
        self,
        input_urls: list[str],
        output_urls: list[str],
        window: int,
    ) -> dict:
        return {
            "input_urls": input_urls,
            "output_urls": output_urls,
            "input": {
                "count": self.count_input,
                "duplicates": self.count_input_duplicates,
            },
            "output": {
                "processed": self.count_processed,
                "success": self.count_success,
                "errors": self.count_error,
                "error_rate": self.error_rate,
            },
            "remaining": self.count_remaining,
            "timing": {
                "first_timestamp": self.first_timestamp,
                "last_timestamp": self.last_timestamp,
                "started_at": self._format_ts(self.first_timestamp),
                "last_record_at": self._format_ts(self.last_timestamp),
            },
            "rates": {
                "overall_pages_per_sec": self.overall_rate,
                "recent_pages_per_sec": self.recent_rate,
                "window": window,
            },
            "eta": {
                "overall": self.eta_overall,
                "recent": self.eta_recent,
            },
        }


class StatusTool:
    def name(self) -> str:
        return "status"

    def _count_input_text(self, urls: Sequence[URL]) -> tuple[int, int]:
        """
        Count lines across all text-format input URLs.

        Returns (total, duplicates).
        """
        seen: set[str] = set()
        total = 0
        for url in urls:
            with url.with_mode("r") as f:
                for line in f:
                    raw = line.strip()
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    total += 1
                    seen.add(raw)
        duplicates = total - len(seen)
        return total, duplicates

    def _count_input_json(self, urls: Sequence[URL]) -> tuple[int, int]:
        """
        Count records across all JSONL-format input URLs.

        Returns (total, duplicates).
        """
        seen: set[str] = set()
        total = 0
        for url in urls:
            with url.with_mode("r") as f:
                for line in f:
                    data = json.loads(line)
                    url_str = data["url"]
                    if isinstance(url_str, bytes):
                        url_str = url_str.decode("utf-8")
                    total += 1
                    seen.add(url_str)
        duplicates = total - len(seen)
        return total, duplicates

    def _count_input_avro(self, urls: Sequence[URL]) -> tuple[int, int]:
        """
        Fast-count records across all Avro-format input URLs using block metadata.

        Duplicate detection is skipped on the fast path.
        Returns (total, 0).
        """
        count_tool = CountTool()
        total = count_tool.count(urls)
        return total, 0

    def count_input(
        self,
        input_urls: Sequence[URL],
        input_format: InputFormat,
    ) -> tuple[int, int]:
        """
        Count URLs in the input file(s).

        Returns (total_count, duplicate_count).
        Duplicate count is 0 for avro format (fast-count path skips full deserialization).
        """
        if input_format == InputFormat.TEXT:
            return self._count_input_text(input_urls)
        elif input_format == InputFormat.JSON:
            return self._count_input_json(input_urls)
        elif input_format == InputFormat.AVRO:
            return self._count_input_avro(input_urls)
        else:
            raise ValueError(f"Unknown input format: {input_format}")

    def scan_output(
        self,
        output_urls: Sequence[URL],
        window: int = DEFAULT_WINDOW,
    ) -> StatusToolResult:
        """
        Scan Avro output file(s) to compute progress statistics.

        Uses PartitionedAvroReader to treat all output files as a single stream.
        """
        result = StatusToolResult()

        # Rolling deque of the last `window` timestamps
        ts_window: deque[int] = deque(maxlen=window)

        try:
            with PartitionedAvroReader(output_urls) as reader:
                for record in reader:
                    if not isinstance(record, dict):
                        continue
                    result.count_processed += 1

                    ts = record.get("timestamp")
                    if isinstance(ts, int):
                        if result.first_timestamp is None:
                            result.first_timestamp = ts
                        result.last_timestamp = ts
                        ts_window.append(ts)

                    if record.get("error") is None:
                        result.count_success += 1
                    else:
                        result.count_error += 1
        except Exception as e:
            # Output file may not exist yet — that's fine, report 0 processed
            logger.debug("Could not read output file(s): %s", e)

        result.window_timestamps = list(ts_window)
        return result

    def status(
        self,
        input_url_strs: list[str],
        output_url_strs: list[str],
        input_format: InputFormat = InputFormat.TEXT,
        window: int = DEFAULT_WINDOW,
    ) -> StatusToolResult:
        # Expand all input URLs (handles globs, directories, cloud paths)
        input_urls = flatten_urls([parse_url(u) for u in input_url_strs])
        output_urls = flatten_urls([parse_url(u) for u in output_url_strs])

        # Count input URLs
        count_input, count_duplicates = self.count_input(input_urls, input_format)

        # Scan output records
        result = self.scan_output(output_urls, window=window)
        result.count_input = count_input
        result.count_input_duplicates = count_duplicates

        return result

    def configure(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(
            self.name(),
            help="Report progress of a crawl run",
        )
        parser.add_argument(
            "--input",
            dest="input_urls",
            nargs="+",
            required=True,
            help="URL(s) containing the list of URLs to crawl (same format as 'crawl --input')",
        )
        parser.add_argument(
            "--output",
            dest="output_urls",
            nargs="+",
            required=True,
            help="URL(s) of the crawl output Avro file(s)",
        )
        parser.add_argument(
            "--input-format",
            dest="input_format",
            type=InputFormat,
            choices=list(InputFormat),
            default=InputFormat.TEXT,
            help="Format of the input URL list (default: text)",
        )
        parser.add_argument(
            "--window",
            type=int,
            default=DEFAULT_WINDOW,
            help=f"Number of recent records used for rolling rate (default: {DEFAULT_WINDOW})",
        )
        parser.add_argument(
            "--json",
            dest="emit_json",
            action="store_true",
            help="Emit machine-readable JSON to stdout",
        )

    def run(self, args: argparse.Namespace) -> None:
        result = self.status(
            input_url_strs=args.input_urls,
            output_url_strs=args.output_urls,
            input_format=args.input_format,
            window=args.window,
        )
        if args.emit_json:
            print(
                json.dumps(
                    result.to_json_dict(
                        input_urls=args.input_urls,
                        output_urls=args.output_urls,
                        window=args.window,
                    ),
                    indent=2,
                )
            )
        else:
            print(
                result.to_text(
                    input_urls=args.input_urls,
                    output_urls=args.output_urls,
                    window=args.window,
                )
            )
