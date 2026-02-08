# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import sys
import subprocess
import tempfile
import logging
import requests
import time

logger = logging.getLogger(__name__)

DEFAULT_CHROME_DEBUG_PORT = 9222


class ChromeTool:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None

    def name(self) -> str:
        return "chrome"

    def start_chrome(
        self,
        headless: bool = False,
        chrome_debug_port: int = DEFAULT_CHROME_DEBUG_PORT,
        proxy_server: str | None = None,
        wait: bool = False,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Build the command to start Chrome
            chrome_command = [
                "google-chrome",
                f"--remote-debugging-port={chrome_debug_port}",
                f"--user-data-dir={tmpdir}",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            if headless:
                chrome_command.append("--headless")
            if proxy_server:
                chrome_command.append(f"--proxy-server={proxy_server}")
            # Start Chrome with the specified command
            logger.info("Starting Chrome with command: %s", " ".join(chrome_command))
            self.proc = subprocess.Popen(
                chrome_command,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            if wait:
                self.proc.wait()

    def wait_for_chrome(
        self,
        chrome_debug_port: int = DEFAULT_CHROME_DEBUG_PORT,
        timeout: int | None = None,
    ) -> None:
        start_time = time.time()
        while timeout is None or (time.time() - start_time) < timeout:
            try:
                res = requests.get(f"http://localhost:{chrome_debug_port}/json")
                if res.status_code == 200:
                    logger.info("Chrome is ready on port %d", chrome_debug_port)
                    return
            except requests.ConnectionError:
                pass
            time.sleep(1)

    def stop_chrome(self) -> None:
        if self.proc:
            logger.info("Stopping Chrome with PID %d", self.proc.pid)
            self.proc.terminate()
            self.proc.wait()
            self.proc = None

    def configure(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name(), help="Runs Chrome")
        parser.add_argument(
            "--headless",
            action="store_true",
            help="Run Chrome in headless mode",
        )
        parser.add_argument(
            "--chrome_debug_port",
            type=int,
            default=DEFAULT_CHROME_DEBUG_PORT,
            help="Open Chrome DevTools Protocol on this port",
        )
        parser.add_argument(
            "--proxy_server",
            help="Proxy server to use (e.g., 'http://localhost:8080')",
        )

    def run(self, args: argparse.Namespace) -> None:
        try:
            self.start_chrome(
                headless=args.headless,
                chrome_debug_port=args.chrome_debug_port,
                proxy_server=args.proxy_server,
                wait=True,
            )
        except KeyboardInterrupt:
            self.stop_chrome()
