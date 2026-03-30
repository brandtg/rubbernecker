# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field


@dataclass
class AvroFileInfo:
    """Metadata about a single .avro file discovered on disk."""

    path: str  # absolute path
    rel_path: str  # path relative to --root
    mtime: float  # os.stat mtime
    record_count: int | None  # None if not yet cached
    schema_name: str | None  # None if not yet read

    @classmethod
    def from_row(cls, row: tuple) -> "AvroFileInfo":
        # row: (path, rel_path, mtime, record_count, schema_name)
        return cls(
            path=row[0],
            rel_path=row[1],
            mtime=row[2],
            record_count=row[3],
            schema_name=row[4],
        )


@dataclass
class DirectoryInfo:
    """A directory under --root containing one or more .avro files."""

    path: str  # absolute path
    rel_path: str  # path relative to --root
    files: list[AvroFileInfo] = field(
        default_factory=list
    )  # all .avro files in this directory
    is_crawl_dataset: bool = False  # True if pages.avro + urls.* present
    input_url_path: str | None = None  # absolute path to urls.* if found
