# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

from .base import Parser, list_parsers
from avrokit import URL, parse_url, create_url_mapping, avro_reader, avro_writer
from avro.schema import Schema
from dataclasses import dataclass
import argparse
import importlib
import importlib.util
import logging
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger("parsetool")


@dataclass
class ParseToolStats:
    count_input: int = 0
    count_output: int = 0
    count_error: int = 0

    def __add__(self, other: "ParseToolStats") -> "ParseToolStats":
        return ParseToolStats(
            count_input=self.count_input + other.count_input,
            count_output=self.count_output + other.count_output,
            count_error=self.count_error + other.count_error,
        )


POISON_PILL = (None, None)  # Signal to workers to stop
WRITE_DONE = (None, None, None)  # Signal that writing is complete


def worker_process(
    parser_class: str,
    script_path: str | None,
    work_queue: multiprocessing.Queue,
    result_queue: multiprocessing.Queue,
) -> None:
    """Worker process that parses records from work_queue and puts results on result_queue."""
    logger.debug("Worker starting")
    try:
        # Initialize parser in worker process
        parser = ParseTool._load_parser_static(parser_class, script_path)
        logger.debug("Worker initialized parser successfully")
    except Exception as e:
        logger.error("Worker failed to initialize parser: %s", e)
        # Signal done so writer doesn't hang
        result_queue.put(("done", None, None, None))
        return

    while True:
        task = work_queue.get()
        if task == POISON_PILL:
            # Signal to writer that this worker is done
            result_queue.put(("done", None, None, None))
            break

        seq_id, record = task
        stats = ParseToolStats()

        try:
            stats.count_input = 1
            results: list[dict[str, Any]] = []
            for parsed_record in parser.parse(record):
                if parsed_record is not None:
                    results.append(cast(dict[str, Any], parsed_record))
                    stats.count_output += 1
            result_queue.put(("result", seq_id, results, stats))
        except Exception as e:
            logger.error("Error parsing record: %s", e)
            if logging.DEBUG == logger.getEffectiveLevel():
                logger.exception(e)
            stats.count_error = 1
            result_queue.put(("result", seq_id, None, stats))


def writer_process(
    output_url: URL,
    schema: Schema,
    result_queue: multiprocessing.Queue,
    num_workers: int,
    stats_accumulator: dict,
) -> None:
    """Writer process that consumes results and writes to Avro."""
    logger.debug("Writer process starting, expecting %d workers", num_workers)
    workers_done = 0

    with avro_writer(output_url.with_mode("wb"), schema) as writer:
        while workers_done < num_workers:
            msg_type, seq_id, results, task_stats = result_queue.get()

            if msg_type == "done":
                workers_done += 1
                continue

            # Accumulate stats
            stats_accumulator["count_input"] += task_stats.count_input
            stats_accumulator["count_output"] += task_stats.count_output
            stats_accumulator["count_error"] += task_stats.count_error

            # Write results
            if results:
                for parsed_record in results:
                    writer.append(parsed_record)

            # Progress logging every 1k records
            total_processed = (
                stats_accumulator["count_output"] + stats_accumulator["count_error"]
            )
            if total_processed % 1000 == 0:
                logger.info(
                    "Progress: input=%d output=%d errors=%d",
                    stats_accumulator["count_input"],
                    stats_accumulator["count_output"],
                    stats_accumulator["count_error"],
                )

        logger.debug("Writer process finished")


class ParseTool:
    def name(self) -> str:
        return "parse"

    @staticmethod
    def _load_parser_static(class_name: str, script_path: str | None = None) -> Parser:
        """Static version of load_parser for use in worker processes."""
        if script_path:
            script_file = Path(script_path).resolve()
            if not script_file.exists():
                raise FileNotFoundError(f"Script file not found: {script_file}")
            module_name = script_file.stem
            spec = importlib.util.spec_from_file_location(module_name, script_file)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load module from {script_file}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return getattr(module, class_name)()
        else:
            module_name, _, class_name = class_name.rpartition(".")
            module = importlib.import_module(module_name)
            return getattr(module, class_name)()

    def load_parser(self, class_name: str, script_path: str | None = None) -> Parser:
        return self._load_parser_static(class_name, script_path)

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

    def parse_parallel(
        self,
        parser: Parser,
        base_input_url: URL,
        base_output_url: URL,
        num_workers: int,
        script_path: str | None = None,
    ) -> ParseToolStats:
        """Parse with process-level parallelism using bounded queues."""
        # Get parser info for worker initialization
        parser_class = parser.__class__.__name__
        # When using a script, just use the class name (module is derived from script filename)
        # When using built-in parser, use full module.class path
        if script_path:
            worker_parser_name = parser_class
        else:
            parser_module = parser.__class__.__module__
            worker_parser_name = f"{parser_module}.{parser_class}"

        stats = ParseToolStats()

        for input_url, output_url in create_url_mapping(
            base_input_url, base_output_url
        ):
            logger.info(
                "Parsing (parallel=%d) %s -> %s", num_workers, input_url, output_url
            )

            # Bounded queues for backpressure (larger to prevent deadlock)
            queue_maxsize = max(100, num_workers * 10)
            work_queue: multiprocessing.Queue = multiprocessing.Queue(
                maxsize=queue_maxsize
            )
            result_queue: multiprocessing.Queue = multiprocessing.Queue(
                maxsize=queue_maxsize
            )

            # Shared stats accumulator
            manager = multiprocessing.Manager()
            shared_stats = manager.dict()
            shared_stats["count_input"] = 0
            shared_stats["count_output"] = 0
            shared_stats["count_error"] = 0

            # Start worker processes
            workers: list[multiprocessing.Process] = []
            for i in range(num_workers):
                p = multiprocessing.Process(
                    target=worker_process,
                    args=(worker_parser_name, script_path, work_queue, result_queue),
                )
                p.start()
                workers.append(p)
                logger.debug("Started worker %d (pid=%d)", i, p.pid)

            # Give workers a moment to initialize
            time.sleep(0.5)

            # Check if any workers died immediately
            dead_workers = [i for i, p in enumerate(workers) if not p.is_alive()]
            if dead_workers:
                raise RuntimeError(
                    f"Workers {dead_workers} died immediately after starting"
                )

            # Start writer process
            writer_p = multiprocessing.Process(
                target=writer_process,
                args=(
                    output_url,
                    parser.schema(),
                    result_queue,
                    num_workers,
                    shared_stats,
                ),
            )
            writer_p.start()

            try:
                # Producer: read records and put on work queue (blocks when full)
                record_count = 0
                logger.info("Starting to read records from %s", input_url)
                with avro_reader(input_url.with_mode("rb")) as reader:
                    logger.info("Avro reader opened successfully")
                    for seq_id, record in enumerate(reader):
                        work_queue.put((seq_id, record))
                        record_count += 1

                logger.info("Finished queuing %d records", record_count)

                # Signal workers to stop
                for _ in range(num_workers):
                    work_queue.put(POISON_PILL)

                # Wait for workers to finish (no timeout - let them work)
                logger.info("Waiting for %d workers to finish...", num_workers)
                for i, p in enumerate(workers):
                    p.join()
                    logger.debug("Worker %d finished", i)

                # Wait for writer to finish (no timeout)
                logger.info("Waiting for writer to finish...")
                writer_p.join()
                logger.debug("Writer finished")

                # Copy stats from shared dict
                stats.count_input += shared_stats["count_input"]
                stats.count_output += shared_stats["count_output"]
                stats.count_error += shared_stats["count_error"]

            except KeyboardInterrupt:
                logger.warning("Interrupted! Shutting down workers...")

                # Terminate workers
                for p in workers:
                    if p.is_alive():
                        p.terminate()
                        p.join(timeout=1)

                if writer_p.is_alive():
                    writer_p.terminate()
                    writer_p.join(timeout=1)

                # Clean up partial output
                logger.warning("Discarding incomplete output for %s", output_url)
                try:
                    output_url.delete()
                except Exception:
                    pass
                raise

        return stats

    def configure(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name(), help="Parse output of crawl")
        parser.add_argument(
            "name",
            help="Name of the parser class to use (e.g., 'StandardPageParser' or 'rubbernecker.parse.standard.StandardPageParser')",
        )
        parser.add_argument(
            "input_url",
            help="URL containing result of crawl",
        )
        parser.add_argument(
            "output_url",
            help="URL to save the parsed data",
        )
        parser.add_argument(
            "--script",
            help="Path to a Python file containing the parser implementation",
        )

        # Calculate default parallelism
        cpu_count = os.cpu_count()
        default_parallelism = max(1, (cpu_count // 2) if cpu_count else 1)

        parser.add_argument(
            "--parallelism",
            type=int,
            default=default_parallelism,
            help=f"Number of parallel worker processes (default: {default_parallelism})",
        )

    def run(self, args: argparse.Namespace) -> None:
        # Validate built-in parser name if no script provided
        if not args.script and args.name not in self.list_parsers():
            raise ValueError(
                f"Unknown parser: {args.name}. "
                f"Use --script to load from a file, or choose from: {', '.join(self.list_parsers())}"
            )

        loaded_parser = self.load_parser(args.name, args.script)
        input_url = parse_url(args.input_url)
        output_url = parse_url(args.output_url)

        if args.parallelism > 1:
            stats = self.parse_parallel(
                loaded_parser, input_url, output_url, args.parallelism, args.script
            )
        else:
            stats = self.parse(loaded_parser, input_url, output_url)

        logger.info("%s (done)", stats)
