# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import asyncio
import base64
from dataclasses import dataclass
import logging
import contextlib
from typing import Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class ProxyAddress:
    host: str
    port: int
    auth: Tuple[str, str] | None = None

    def auth_token(self) -> str | None:
        if self.auth:
            username, password = self.auth
            return base64.b64encode(f"{username}:{password}".encode()).decode()
        return None


class ProxyTool:
    def name(self) -> str:
        return "proxy"

    def _create_connect_request(self, target: str, upstream_auth: str | None) -> str:
        if upstream_auth:
            return (
                f"CONNECT {target} HTTP/1.1\r\n"
                f"Host: {target}\r\n"
                f"Proxy-Connection: Keep-Alive\r\n"
                f"Proxy-Authorization: Basic {upstream_auth}\r\n"
                "\r\n"
            )
        else:
            return (
                f"CONNECT {target} HTTP/1.1\r\n"
                f"Host: {target}\r\n"
                f"Proxy-Connection: Keep-Alive\r\n"
                "\r\n"
            )

    def _create_handler(
        self,
        upstream: ProxyAddress,
    ):
        # Create HTTP basic authentication header for upstream proxy
        upstream_auth = upstream.auth_token()

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                # Read the incoming request
                request_line = await reader.readuntil(b"\r\n")
                method, target, _ = request_line.decode().strip().split()
                headers = await reader.readuntil(b"\r\n\r\n")
                # Connect to upstream proxy
                try:
                    upstream_reader, upstream_writer = await asyncio.open_connection(
                        upstream.host, upstream.port
                    )
                except Exception as e:
                    logger.error("Upstream connection failed: %s", e)
                    writer.close()
                    await writer.wait_closed()
                    return
                if method.upper() == "CONNECT":
                    # Handle CONNECT method
                    connect_req = self._create_connect_request(target, upstream_auth)
                    upstream_writer.write(connect_req.encode())
                    await upstream_writer.drain()
                    # Relay response back to client
                    response = await upstream_reader.readuntil(b"\r\n\r\n")
                    writer.write(response)
                    await writer.drain()
                else:
                    # Proxy other HTTP methods
                    upstream_writer.write(
                        f"{method} {target} HTTP/1.1\r\n"
                        f"Proxy-Authorization: Basic {upstream_auth}\r\n".encode()
                        + headers
                    )
                    await upstream_writer.drain()

                async def pipe(src_reader, dst_writer):
                    try:
                        while True:
                            data = await src_reader.read(4096)
                            if not data:
                                break
                            dst_writer.write(data)
                            await dst_writer.drain()
                    except Exception as e:
                        logger.error("Pipe error: %s", e)
                    finally:
                        try:
                            dst_writer.close()
                            await dst_writer.wait_closed()
                        except Exception:
                            pass

                # Proxy streams
                task1 = asyncio.create_task(pipe(reader, upstream_writer))
                task2 = asyncio.create_task(pipe(upstream_reader, writer))
                done, pending = await asyncio.wait(
                    [task1, task2],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    if task.exception():
                        logger.error("Task error: %s", task.exception())
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

            except Exception as e:
                logger.error("Handler error: %s", e)

        return handle

    async def start_proxy(self, upstream: ProxyAddress, listen: ProxyAddress):
        handler = self._create_handler(upstream)
        server = await asyncio.start_server(
            handler,
            listen.host,
            listen.port,
        )
        logger.info("Listening on %s:%d", listen.host, listen.port)
        async with server:
            await server.serve_forever()

    def configure(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name(), help="Run an asyncio proxy server")
        parser.add_argument(
            "upstream",
            type=str,
            help="Upstream proxy URL",
        )
        parser.add_argument(
            "listen",
            type=str,
            help="Local proxy URL",
            nargs="?",
            default="127.0.0.1:3128",
        )

    def _parse_address(self, url: str) -> ProxyAddress:
        if "://" not in url:
            url = "//" + url  # Prepend dummy scheme if missing
        parsed = urlparse(url)
        if not parsed.hostname:
            raise ValueError("Invalid URL: missing hostname")
        if not parsed.port:
            raise ValueError("Invalid URL: missing port")
        if (
            parsed.username
            and not parsed.password
            or parsed.password
            and not parsed.username
        ):
            raise ValueError(
                "Invalid URL: must have both username and password for auth"
            )
        return ProxyAddress(
            host=parsed.hostname,
            port=parsed.port,
            auth=(
                (
                    parsed.username,
                    parsed.password,
                )
                if parsed.username and parsed.password
                else None
            ),
        )

    def run(self, args: argparse.Namespace) -> None:
        try:
            upstream = self._parse_address(args.upstream)
            listen = self._parse_address(args.listen)
            asyncio.run(self.start_proxy(upstream, listen))
        except KeyboardInterrupt:
            logger.info("Proxy shutdown requested by user.")
