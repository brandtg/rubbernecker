# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import logging
import os

from avrokit import avro_reader, parse_url
from avrokit.tools.count import CountTool

from rubbernecker.server.cache import get_cached, init_db, set_cached
from rubbernecker.server.models import AvroFileInfo, DirectoryInfo

logger = logging.getLogger(__name__)

# Priority order for URL input files
_URL_FILENAMES = ["urls.txt", "urls.jsonl", "urls.avro"]


def find_avro_files(root: str) -> list[AvroFileInfo]:
    """
    Walk `root` recursively and return an AvroFileInfo for each .avro file found.
    record_count and schema_name are left as None (populated later by the cache layer).
    """
    results: list[AvroFileInfo] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if not filename.endswith(".avro"):
                continue
            abs_path = os.path.join(dirpath, filename)
            try:
                stat = os.stat(abs_path)
                mtime = stat.st_mtime
            except OSError:
                continue
            rel_path = os.path.relpath(abs_path, root)
            results.append(
                AvroFileInfo(
                    path=abs_path,
                    rel_path=rel_path,
                    mtime=mtime,
                    record_count=None,
                    schema_name=None,
                )
            )
    return results


def _get_schema_name(path: str) -> str | None:
    """Extract the top-level Avro schema name from an Avro file."""
    try:
        with avro_reader(parse_url(path).with_mode("rb")) as reader:
            return reader.datum_reader.writers_schema.name
    except Exception:
        return None


def _get_record_count(path: str) -> int | None:
    """Count records in an Avro file using CountTool (fast block-level counting)."""
    try:
        count_tool = CountTool()
        return count_tool.count([parse_url(path)])
    except Exception:
        return None


def discover_directories(root: str, db_path: str) -> list[DirectoryInfo]:
    """
    Walk root, group .avro files by parent directory, populate record counts
    (from cache or fresh read), and classify crawl datasets.
    Returns a list of DirectoryInfo sorted by rel_path.
    """
    init_db(db_path)
    avro_files = find_avro_files(root)

    # Group files by parent directory (absolute path)
    dir_map: dict[str, list[AvroFileInfo]] = {}
    for f in avro_files:
        dir_abs = os.path.dirname(f.path)
        dir_map.setdefault(dir_abs, []).append(f)

    directories: list[DirectoryInfo] = []
    for dir_abs, files in dir_map.items():
        dir_rel = os.path.relpath(dir_abs, root)

        # Populate record_count and schema_name for each file
        for file_info in files:
            cached = get_cached(db_path, file_info.path, file_info.mtime)
            if cached is not None:
                count, sname = cached
                file_info.record_count = count
                file_info.schema_name = sname if sname else None
            else:
                record_count = _get_record_count(file_info.path)
                schema_name = _get_schema_name(file_info.path)
                if record_count is not None:
                    file_info.record_count = record_count
                    file_info.schema_name = schema_name
                    set_cached(
                        db_path,
                        file_info.path,
                        file_info.mtime,
                        record_count,
                        schema_name or "",
                    )

        # Determine if this is a crawl dataset
        filenames_in_dir = {os.path.basename(f.path) for f in files}
        is_crawl = "pages.avro" in filenames_in_dir
        input_url_path: str | None = None
        if is_crawl:
            for url_filename in _URL_FILENAMES:
                candidate = os.path.join(dir_abs, url_filename)
                if os.path.isfile(candidate):
                    input_url_path = candidate
                    break
            # If no urls.* companion found, it's not really a crawl dataset
            if input_url_path is None:
                is_crawl = False

        directories.append(
            DirectoryInfo(
                path=dir_abs,
                rel_path=dir_rel,
                files=files,
                is_crawl_dataset=is_crawl,
                input_url_path=input_url_path,
            )
        )

    directories.sort(key=lambda d: d.rel_path)
    return directories
