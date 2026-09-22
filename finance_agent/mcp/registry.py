"""Shared broker MCP utilities."""
from __future__ import annotations
from langchain_core.tools import BaseTool


def namespace_tools(provider: str, tools: list[BaseTool]) -> list[BaseTool]:
    """Return tools with broker-qualified names while preserving MCP callbacks."""
    return [tool.model_copy(update={"name": f"{provider}_{tool.name}"}) for tool in tools]

class BrokerMCPRegistry:
    """Combine broker MCP clients while retaining each client's lifecycle."""
    def __init__(self, clients):
        self._clients = list(clients)
        self._connected = []

    async def connect(self):
        if self._connected:
            return
        try:
            for client in self._clients:
                await client.connect()
                self._connected.append(client)
        except BaseException:
            await self.aclose()
            raise

    async def discover_tools(self):
        tools = []
        for client in self._connected:
            tools.extend(await client.discover_tools())
        names = [tool.name for tool in tools]
        if len(names) != len(set(names)):
            raise RuntimeError("Broker MCP tool-name collision after namespacing.")
        return tools

    async def aclose(self):
        for client in reversed(self._connected):
            await client.aclose()
        self._connected = []
