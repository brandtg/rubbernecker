# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import argparse

from rubbernecker.server.app import create_app
from rubbernecker.server.tool import ServerTool


def test_server_tool_name():
    assert ServerTool().name() == "server"


def test_server_tool_configure_registers_subcommand():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="tool")
    ServerTool().configure(subparsers)
    args = parser.parse_args(["server", "--root", "/tmp"])
    assert args.root == "/tmp"
    assert args.host == "127.0.0.1"
    assert args.port == 7707


def test_server_tool_configure_custom_host_port():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="tool")
    ServerTool().configure(subparsers)
    args = parser.parse_args(
        ["server", "--root", "/tmp", "--host", "0.0.0.0", "--port", "8080"]
    )
    assert args.root == "/tmp"
    assert args.host == "0.0.0.0"
    assert args.port == 8080


def test_create_app_stores_root():
    app = create_app(root="/some/path")
    assert app.config["ROOT"] == "/some/path"
