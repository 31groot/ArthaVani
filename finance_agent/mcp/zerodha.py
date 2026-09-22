"""Read-only client for Zerodha's official self-hosted Kite MCP server."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AsyncExitStack
import os
from pathlib import Path
import re
import shutil
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Tool

from config.logger import logger
from config.settings import settings
from finance_agent.mcp.registry import namespace_tools

READ_ONLY_TOOLS = frozenset({
    "get_gtts", "get_historical_data", "get_holdings", "get_ltp",
    "get_margins", "get_mf_holdings", "get_ohlc", "get_order_history",
    "get_order_trades", "get_orders", "get_positions", "get_profile",
    "get_quotes", "get_trades", "search_instruments",
})
SERVER_EXCLUDED_TOOLS = (
    "place_order", "modify_order", "cancel_order",
    "place_gtt_order", "modify_gtt_order", "delete_gtt_order",
)


class ZerodhaMCPClient:
    """Manage the official local Kite MCP server and one MCP HTTP session."""
    def __init__(self, url: str | None = None, *, transport_factory: Callable[..., Any] = streamablehttp_client, session_factory: Callable[..., Any] = ClientSession, start_server: bool = True, server_dir: str | Path | None = None) -> None:
        self._url = url or settings.ZERODHA_MCP_URL
        self._transport_factory = transport_factory
        self._session_factory = session_factory
        self._start_server = start_server
        self._server_dir = Path(server_dir or settings.ZERODHA_KITE_SERVER_DIR).resolve()
        self._server_process: asyncio.subprocess.Process | None = None
        self._stack: AsyncExitStack | None = None
        self._session: Any | None = None
        self._close_lock = asyncio.Lock()

    @property
    def session(self) -> Any:
        if self._session is None:
            raise RuntimeError("Zerodha MCP client is not connected.")
        return self._session

    @staticmethod
    def filter_read_only_tools(tools: list[Tool]) -> list[Tool]:
        return [tool for tool in tools if tool.name in READ_ONLY_TOOLS]

    async def _start_official_server(self) -> None:
        if not self._start_server:
            return
        if not self._server_dir.joinpath("go.mod").is_file():
            raise RuntimeError(f"Official Kite MCP checkout not found: {self._server_dir}")
        go = shutil.which("go")
        if go is None:
            raise RuntimeError("Go is required to build the official Kite MCP server.")
        binary = self._server_dir / ".kite-mcp-server"
        build = await asyncio.create_subprocess_exec(go, "build", "-o", str(binary), ".", cwd=str(self._server_dir), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, error = await build.communicate()
        if build.returncode != 0:
            raise RuntimeError("Official Kite MCP server build failed.")
        environment = os.environ.copy()
        environment.update({
            "KITE_API_KEY": settings.KITE_API_KEY or "",
            "KITE_API_SECRET": settings.KITE_API_SECRET or "",
            "APP_MODE": "http",
            "APP_HOST": settings.ZERODHA_KITE_HOST,
            "APP_PORT": str(settings.ZERODHA_KITE_PORT),
            "PUBLIC_BASE_URL": settings.ZERODHA_KITE_PUBLIC_BASE_URL,
            "EXCLUDED_TOOLS": ",".join(SERVER_EXCLUDED_TOOLS),
            # Official server logs request tokens at INFO; suppress them.
            "LOG_LEVEL": "warn",
        })
        self._server_process = await asyncio.create_subprocess_exec(str(binary), cwd=str(self._server_dir), env=environment, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        host, port = settings.ZERODHA_KITE_HOST, settings.ZERODHA_KITE_PORT
        for _ in range(100):
            if self._server_process.returncode is not None:
                self._server_process = None
                raise RuntimeError("Official Kite MCP server exited during startup.")
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 0.2)
                writer.close()
                await writer.wait_closed()
                return
            except (OSError, asyncio.TimeoutError):
                await asyncio.sleep(0.1)
        raise RuntimeError("Official Kite MCP server did not become ready.")

    async def connect(self) -> None:
        if self._session is not None:
            return
        await self._start_official_server()
        stack = AsyncExitStack()
        try:
            streams = await stack.enter_async_context(self._transport_factory(self._url))
            read_stream, write_stream, _session_id_getter = streams
            session = await stack.enter_async_context(self._session_factory(read_stream, write_stream))
            await session.initialize()
        except asyncio.CancelledError:
            await stack.aclose()
            await self._stop_server()
            raise
        except Exception:
            await stack.aclose()
            await self._stop_server()
            raise
        self._stack, self._session = stack, session
        logger.info("Connected to local official Zerodha Kite MCP server.")

    async def list_tools(self) -> list[Tool]:
        tools = self.filter_read_only_tools(list((await self.session.list_tools()).tools))
        for tool in tools:
            logger.info("Zerodha read-only MCP tool: %s — %s", tool.name, tool.description or "")
        return tools

    async def get_tools(self) -> list[Tool]:
        return await self.list_tools()

    @staticmethod
    def extract_login_url(result: Any) -> str | None:
        if bool(getattr(result, "isError", False)):
            return None
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                match = re.search(r"https://[^\s\"'<>]+", text)
                if match:
                    return match.group(0).rstrip(".,)")
        return None

    async def authenticate(self) -> str | None:
        result = await self.session.call_tool("login", {})
        return self.extract_login_url(result)

    async def discover_tools(self) -> list[BaseTool]:
        allowed = {tool.name for tool in await self.list_tools()}
        all_tools = list(await load_mcp_tools(self.session))
        return namespace_tools("zerodha", [tool for tool in all_tools if tool.name in allowed])

    async def _stop_server(self) -> None:
        process, self._server_process = self._server_process, None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def close(self) -> None:
        async with self._close_lock:
            stack, self._stack = self._stack, None
            self._session = None
            if stack is not None:
                await stack.aclose()
            await self._stop_server()

    async def aclose(self) -> None:
        await self.close()
