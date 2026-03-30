# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import json

from avrokit import avro_reader, parse_url


def get_schema_json(path: str) -> str | None:
    """Return the Avro schema as a pretty-printed JSON string, or None on error."""
    try:
        with avro_reader(parse_url(path).with_mode("rb")) as reader:
            raw = reader.get_meta("avro.schema")
            if raw is None:
                return None
            return json.dumps(json.loads(raw.decode("utf-8")), indent=2)
    except Exception:
        return None


def get_records_page(path: str, offset: int, limit: int) -> tuple[list[dict], bool]:
    """
    Return (records, has_more) where records are up to `limit` records starting
    at `offset`. has_more is True if there are records beyond offset+limit.
    Never holds more than limit+1 records in memory.
    """
    try:
        with avro_reader(parse_url(path).with_mode("rb")) as reader:
            records: list[dict] = []
            has_more = False
            idx = 0
            for record in reader:
                if idx < offset:
                    idx += 1
                    continue
                if idx < offset + limit:
                    records.append(dict(record))
                    idx += 1
                else:
                    # There is at least one more record beyond the page
                    has_more = True
                    break
            return records, has_more
    except Exception:
        return [], False
