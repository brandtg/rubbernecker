# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

from rubbernecker.server.models import AvroFileInfo


def order_pipeline_stages(files: list[AvroFileInfo]) -> list[AvroFileInfo]:
    return sorted(files, key=lambda f: (f.mtime, f.path))


def compute_deltas(files: list[AvroFileInfo]) -> list[int | None]:
    deltas: list[int | None] = []
    for i, f in enumerate(files):
        if i == 0:
            deltas.append(None)
        else:
            prev = files[i - 1]
            if f.record_count is None or prev.record_count is None:
                deltas.append(None)
            else:
                deltas.append(f.record_count - prev.record_count)
    return deltas
