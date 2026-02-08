# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
from typing import Protocol


class Tool(Protocol):
    def name(self) -> str: ...
    def configure(self, subparsers: argparse._SubParsersAction) -> None: ...
    def run(self, args: argparse.Namespace) -> None: ...
