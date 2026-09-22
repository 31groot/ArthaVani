"""Explicit live test; requires Groww credentials in the environment."""
import asyncio
from finance_agent.mcp.groww import GrowwMCPClient

async def main():
    client = GrowwMCPClient()
    try:
        await client.connect()
        print("Local Groww MCP initialized.")
        for tool in await client.list_tools(): print(f"{tool.name}: {tool.description}")
        result = await client.session.call_tool("get_user_profile", {})
        print("Authenticated get_user_profile succeeded.", bool(result.content))
    finally:
        await client.close()
if __name__ == "__main__": asyncio.run(main())
