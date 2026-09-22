"""MCP client for ArthaVani's local Groww SDK-backed MCP server."""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
import sys
from pathlib import Path
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool
from config.logger import logger
from finance_agent.mcp.registry import namespace_tools

REPO_ROOT = Path(__file__).resolve().parents[2]


class GrowwMCPClient:
    """Async lifecycle client for the local, read-only Groww MCP subprocess."""
    def __init__(self, command: str | None = None, args: list[str] | None = None) -> None:
        self._command = command or sys.executable
        self._args = args or ["-m", "finance_agent.mcp.server"]
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._close_lock = asyncio.Lock()

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("Groww MCP client is not connected.")
        return self._session

    async def connect(self) -> None:
        if self._session is not None:
            return
        stack = AsyncExitStack()
        try:
            streams = await stack.enter_async_context(stdio_client(StdioServerParameters(
                command=self._command, args=self._args, cwd=str(REPO_ROOT)
            )))
            session = await stack.enter_async_context(ClientSession(*streams))
            await session.initialize()
        except asyncio.CancelledError:
            await stack.aclose()
            raise
        except Exception:
            await stack.aclose()
            raise
        self._stack, self._session = stack, session
        logger.info("Connected to local Groww MCP server.")

    async def list_tools(self) -> list[Tool]:
        tools = list((await self.session.list_tools()).tools)
        for tool in tools:
            logger.info("Groww MCP tool: %s — %s", tool.name, tool.description or "")
        return tools

    async def discover_tools(self) -> list[BaseTool]:
        await self.list_tools()
        return namespace_tools("groww", list(await load_mcp_tools(self.session)))

    async def close(self) -> None:
        async with self._close_lock:
            stack, self._stack = self._stack, None
            self._session = None
            if stack is not None:
                await stack.aclose()

    async def aclose(self) -> None:
        await self.close()
