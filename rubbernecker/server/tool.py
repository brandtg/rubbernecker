# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import argparse


class ServerTool:
    def name(self) -> str:
        return "server"

    def configure(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("server", help="Start the admin server")
        parser.add_argument("--root", required=True, help="Root directory to monitor")
        parser.add_argument(
            "--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)"
        )
        parser.add_argument(
            "--port", type=int, default=7707, help="Bind port (default: 7707)"
        )

    def run(self, args: argparse.Namespace) -> None:
        from rubbernecker.server.app import create_app

        app = create_app(root=args.root)
        app.run(host=args.host, port=args.port, threaded=True)
