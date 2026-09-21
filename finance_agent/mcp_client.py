from contextlib import AsyncExitStack
import sys
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools

from mcp import (
    ClientSession,
    StdioServerParameters,
)

from mcp.client.stdio import stdio_client

from config.logger import logger


# Find the root directory of the repository.
#
# __file__:
#     path of this Python file
#
# resolve():
#     converts it to an absolute path
#
# parents[1]:
#     moves up two directory levels
#
# This directory is used as the working directory when
# starting the PersonalFinance MCP server.
REPO_ROOT = Path(
    __file__
).resolve().parents[1]

# Default list for the Arguments passed to the command 
# python -m personal_finance_mcp.server (Default)
DEFAULT_ARGS_LIST = [ "-m", "personal_finance_mcp.server",]

# These are the tools that the PersonalFinance MCP server
# is expected to expose.

# frozenset is used because tool ordering doesn't matter.
PERSONAL_FINANCE_TOOL_NAMES = frozenset(
    {
        "get_account_balance",
        "get_transaction_history",
        "get_portfolio_summary",
        "get_expense_breakdown",
        "get_stock_quote",
    }
)


class PersonalFinanceMCPClient:

    # Async MCP client that starts the PersonalFinance MCP server
    # as a subprocess and communicates with it


    def __init__(
        self,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        cwd: str | None = None,
    ) -> None:

        # Python executable used to start the MCP server.
        
        # sys.executable means:
        #     "Use the same Python interpreter that is running
        #      this application."
        #

        self._command = (
            command
            or sys.executable
        )

        # Arguments passed to the command.
        #
        # Default:
        #     python -m personal_finance_mcp.server
        self._args = (
            args
            or DEFAULT_ARGS_LIST
        )

        # Working directory used when starting the MCP server.
        #
        # Defaults to the repository root.
        self._cwd = (
            cwd
            or str(REPO_ROOT)
        )

        # AsyncExitStack owns the resources used by the MCP connection.
        #
        # Resources such as stdio_client() and ClientSession()
        # are async context managers, and the stack lets us keep
        # them alive across multiple methods.
        self._stack: AsyncExitStack | None = None

        # Active MCP session.
        #
        # None means we are currently disconnected.
        self._session: ClientSession | None = None

    @property
    def session(self) -> ClientSession:

        # Only allow access to the session after connect() has
        # successfully completed.
        if self._session is None:

            raise RuntimeError(
                "MCP client is not connected."
            )

        return self._session

    async def connect(
        self,
    ) -> None:

        # If already connected, don't create a second MCP session.
        if self._session is not None:
            return

        # Describe how the MCP server should be started.
        #
        # Example:
        #
        #     command = /path/to/python
        #     args    = ["-m", "personal_finance_mcp.server"]
        #     cwd     = /path/to/ArthaVani
        params = StdioServerParameters(
            command=self._command,
            args=self._args,
            cwd=self._cwd,
        )

        # Create a resource stack to manage the lifetime of the
        # MCP server process, stdio streams, and session.
        stack = AsyncExitStack()

        try:

            # Start the MCP server as a subprocess and obtain
            # two communication streams:
            #
            #     read_stream  → server → client
            #     write_stream → client → server
            #
            # These are the transport layer for MCP communication.
            read_stream, write_stream = (
                await stack.enter_async_context(
                    stdio_client(params)
                )
            )

            # Create an MCP ClientSession on top of those streams.
            #
            # This handles the MCP protocol rather than making us
            # manually communicate over raw stdin/stdout.
            session = (
                await stack.enter_async_context(
                    ClientSession(
                        read_stream,
                        write_stream,
                    )
                )
            )

            # Perform the MCP initialization handshake.
            #
            # After this succeeds, the client and server know
            # that the MCP session is ready for normal requests.
            await session.initialize()

        except Exception:

            # If anything failed after some resources were opened,
            # close everything that was successfully created.
            await stack.aclose()

            # Re-raise the original exception so the caller can
            # see that connection failed.
            raise

        # Only save the resources after the complete connection
        # and initialization process succeeded.
        self._stack = stack
        self._session = session

        logger.info(
            "Connected to PersonalFinance MCP server."
        )

    async def discover_tools(
        self,
    ) -> list[BaseTool]:

        # Ask the MCP server for its available tools.
        #
        # load_mcp_tools() converts the MCP tool definitions into
        # LangChain BaseTool objects that LangGraph can use.
        tools = await load_mcp_tools(
            self.session
        )

        # Create a set containing the discovered tool names.
        names = {
            tool.name for tool in tools
        }

        # Make sure the MCP server exposes exactly the tools
        # expected by the finance agent.
        #
        # This catches:
        #
        #   - missing tools
        #   - unexpected tools
        #   - incorrect server configuration
        if names != PERSONAL_FINANCE_TOOL_NAMES:

            expected = ", ".join(
                sorted(
                    PERSONAL_FINANCE_TOOL_NAMES
                )
            )

            actual = ", ".join(
                sorted(names)
            )

            raise RuntimeError(
                f"Expected MCP tools [{expected}], "
                f"discovered [{actual}]."
            )

        logger.info(
            "Discovered PersonalFinance MCP tools: %s",
            sorted(names),
        )

        # Return the LangChain-compatible tools to the caller.
        return tools

    async def aclose(
        self,
    ) -> None:

        # Mark the session as unavailable immediately.
        self._session = None

        # Nothing to close if connect() never successfully created
        # an exit stack.
        if self._stack is None:
            return

        # Close every resource managed by AsyncExitStack.
        #
        # This handles cleanup of the MCP session, stdio streams,
        # and the MCP server subprocess.
        await self._stack.aclose()

        # Reset the stack reference so the client is ready for
        # a future connect() call.
        self._stack = None

        logger.info(
            "Disconnected from PersonalFinance MCP server."
        )