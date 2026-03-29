# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
from typing import Protocol

AVRO_CODEC = os.environ.get("AVRO_CODEC", "deflate")


class Tool(Protocol):
    def name(self) -> str: ...
    def configure(self, subparsers: argparse._SubParsersAction) -> None: ...
    def run(self, args: argparse.Namespace) -> None: ...
