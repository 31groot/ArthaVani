"""Explicit live Zerodha hosted-MCP authentication diagnostic."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from finance_agent.mcp.zerodha import ZerodhaMCPClient


async def run_manual_flow(
    client: Any,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[..., None] = print,
) -> None:
    """Run the complete login/profile flow on one client and MCP session."""
    await client.connect()
    print_fn("MCP connection successful.")

    tools = await client.list_tools()
    print_fn("Tool discovery successful:", ", ".join(tool.name for tool in tools))

    login_url = await client.authenticate()
    if not login_url:
        print_fn("Login URL generated: no")
        print_fn("Authenticated get_profile failed: no login URL was returned.")
        return

    print_fn("Login URL generated.")
    print_fn(login_url)
    print_fn("Waiting for browser authentication...")
    input_fn(
        "Open the URL above in your browser and complete the Kite login. "
        "After the browser shows that login was successful, press Enter here."
    )
    print_fn("Browser authentication step completed by user.")

    # Deliberately use the existing session; do not create or reconnect a client.
    result = await client.session.call_tool("get_profile", {})
    if result.isError:
        print_fn("Authenticated get_profile failed.")
    else:
        print_fn("Authenticated get_profile succeeded.")


async def main() -> None:
    client = ZerodhaMCPClient()
    try:
        await run_manual_flow(client)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
