import asyncio
import json
from typing import Any

# MCP's built-in type definitions.
#
# We use these to describe:
#
#     - tools
#     - tool results
#     - text content
import mcp.types as types

# Low-level MCP server implementation.
#
# Server is responsible for handling MCP protocol messages
# and dispatching requests to our handlers.
from mcp.server.lowlevel import Server

# stdio_server() creates the transport used to communicate
# with the MCP client through stdin/stdout.
from mcp.server.stdio import stdio_server

# Database setup and initial demo-data creation.
from personal_finance_mcp.database import (
    DEFAULT_DATABASE_PATH,
    seed_database,
)
from personal_finance_mcp.service import PersonalFinanceService


service = PersonalFinanceService()


# Create the SQLite database and seed it with demo data
# if it does not already contain data.

seed_database(DEFAULT_DATABASE_PATH)



# TOOLS describes the tools that the MCP client can discover.
#

TOOLS = [

    # Tool 1: Account balance

    types.Tool(
        name="get_account_balance",

        # Description is shown to the client/LLM.
        #
        # This helps the model understand when it should use
        # this tool.
        description=(
            "Return the current balance for checking, "
            "savings, or credit_card."
        ),

        # JSON Schema describing the tool's input.
        inputSchema={
            "type": "object",

            # Tool parameters.
            "properties": {
                "account_type": {
                    "type": "string",
                }
            },

            # This argument MUST be supplied.
            "required": ["account_type"],

            # Do not allow parameters that were not declared.
            "additionalProperties": False,
        },
    ),

    # Tool 2: Transaction history

    types.Tool(
        name="get_transaction_history",

        description=(
            "Return up to 50 recent transactions "
            "for a supported account type."
        ),

        inputSchema={
            "type": "object",

            "properties": {

                # Which account should be queried?
                "account_type": {
                    "type": "string",
                },

                # How many transactions should be returned?
                "n": {
                    "type": "integer",

                    # Don't allow zero or negative values.
                    "minimum": 1,

                    # Protect the tool from requesting
                    # an unnecessarily large number of rows.
                    "maximum": 50,
                },
            },

            # Both arguments are required.
            "required": [
                "account_type",
                "n",
            ],

            # Reject any other argument names.
            "additionalProperties": False,
        },
    ),

    # Tool 3: Portfolio summary
    types.Tool(
        name="get_portfolio_summary",

        description=(
            "Return holdings, total market value, "
            "and unrealized gains."
        ),

        inputSchema={
            "type": "object",

            # This tool does not need any input.
            "properties": {},

            # Reject any arguments.
            "additionalProperties": False,
        },
    ),

    # Tool 4: Expense breakdown
    types.Tool(
        name="get_expense_breakdown",

        description=(
            "Return expenses by category for this_month, "
            "last_month, last_30_days, or year_to_date."
        ),

        inputSchema={
            "type": "object",

            "properties": {
                "period": {
                    "type": "string",
                }
            },

            # period must be provided.
            "required": ["period"],

            # Reject unknown parameters.
            "additionalProperties": False,
        },
    ),

    # Tool 5: Stock quote
    types.Tool(
        name="get_stock_quote",

        description=(
            "Return a mock USD market quote "
            "for a supported stock ticker."
        ),

        inputSchema={
            "type": "object",

            "properties": {
                "ticker": {
                    "type": "string",
                }
            },

            # ticker is mandatory.
            "required": ["ticker"],

            # Don't accept undeclared parameters.
            "additionalProperties": False,
        },
    ),
]


# PYTHON FUNCTIONS THAT IMPLEMENT THE TOOLS
#
# These functions connect the MCP tool layer to the actual
# PersonalFinanceService.


def get_account_balance(
    account_type: str,
) -> dict[str, object]:

    # Delegate the actual finance operation to the service.
    return service.get_account_balance(
        account_type
    )


def get_transaction_history(
    account_type: str,
    n: int,
) -> dict[str, object]:

    # Ask the service for the requested transaction history.
    return service.get_transaction_history(
        account_type,
        n,
    )


def get_portfolio_summary() -> dict[str, object]:

    # Portfolio summary does not require any arguments.
    return service.get_portfolio_summary()


def get_expense_breakdown(
    period: str,
) -> dict[str, object]:

    # Delegate expense calculations to the service layer.
    return service.get_expense_breakdown(
        period
    )


def get_stock_quote(
    ticker: str,
) -> dict[str, object]:

    # Ask the service to retrieve the stock quote.
    return service.get_stock_quote(
        ticker
    )



# MAP TOOL NAMES TO THEIR PYTHON HANDLERS
#
# MCP gives us the tool name as a string:
#
#     "get_account_balance"
#
# We need to turn that string into:
#
#     get_account_balance(...)


TOOL_HANDLERS = {

    "get_account_balance": lambda arguments: (
        get_account_balance(
            arguments["account_type"]
        )
    ),

    "get_transaction_history": lambda arguments: (
        get_transaction_history(
            arguments["account_type"],
            arguments["n"],
        )
    ),

    # No arguments are needed for this tool.
    "get_portfolio_summary": lambda arguments: (
        get_portfolio_summary()
    ),

    "get_expense_breakdown": lambda arguments: (
        get_expense_breakdown(
            arguments["period"]
        )
    ),

    "get_stock_quote": lambda arguments: (
        get_stock_quote(
            arguments["ticker"]
        )
    ),
}


# EXPECTED ARGUMENTS FOR EACH TOOL

# This dictionary is used for additional validation.
#
# It tells the server exactly which argument names are allowed.


TOOL_ARGUMENTS = {

    "get_account_balance": {
        "account_type"
    },

    "get_transaction_history": {
        "account_type",
        "n",
    },

    "get_portfolio_summary": set(),

    "get_expense_breakdown": {
        "period"
    },

    "get_stock_quote": {
        "ticker"
    },
}


# STANDARDIZED ERROR RESPONSE
#
# MCP tool calls need a structured result.
#
# Rather than repeating the same error-result construction
# everywhere, we put it into one helper function.


def _error_result(
    message: str,
) -> types.CallToolResult:

    # Put the human-readable error into a small dictionary.
    
    error = {
        "error": message
    }

    # Return an MCP CallToolResult.
    return types.CallToolResult(

        # Human-readable/text representation of the result.
        content=[
            types.TextContent(
                type="text",

                # Convert the dictionary into JSON text.
                #
                # separators removes unnecessary spaces.
                text=json.dumps(
                    error,
                    separators=(",", ":"),
                ),
            )
        ],

        # Also provide the structured dictionary directly.
        structuredContent=error,

        # Tell the MCP client this tool execution represents
        # an error.
        isError=True,
    )


# CREATE THE MCP SERVER

# Create the actual low-level MCP server.
#
# "PersonalFinance" is the server name.
#
# version identifies the server version.
#
# instructions provide additional information to the client
# about what this server is for.
mcp = Server(
    "PersonalFinance",
    version="0.1.0",
    instructions=(
        "Read-only personal-finance demo data."
    ),
)

# MCP: LIST AVAILABLE TOOLS

@mcp.list_tools()
async def list_tools() -> list[types.Tool]:

    # MCP clients call this handler when they ask:
    #
    #     "What tools do you provide?"
    #
    # Return the tool definitions created above.
    return TOOLS


# MCP: EXECUTE A TOOL

@mcp.call_tool()
async def call_tool(
    name: str,
    arguments: dict[str, Any] | None,
) -> types.CallToolResult:

    # Look up the Python handler associated with the requested
    # tool name.
    
    handler = TOOL_HANDLERS.get(name)

    # If the tool name is not registered, return an MCP error.
    if handler is None:

        return _error_result(
            f"Unknown tool '{name}'."
        )

    # The MCP client may send no arguments.
    #
    # Convert None into an empty dictionary so that the rest
    # of the function can always work with a dictionary.
    
    call_arguments = arguments or {}

    # Find arguments that were supplied but are NOT expected.
    
    unexpected = (
        set(call_arguments)
        - TOOL_ARGUMENTS[name]
    )

    # Reject unexpected parameters.
    #
    # This gives us an extra validation layer in addition
    # to the inputSchema exposed to the MCP client.
    if unexpected:

        return _error_result(
            (
                "Unexpected argument(s): "
                f"{', '.join(sorted(unexpected))}."
            )
        )

    try:

        # Execute the selected tool handler.
        
        result = handler(
            call_arguments
        )

    # Handle common input/argument/data errors.
    #
    # AttributeError:
    #     expected attribute was missing
    #
    # KeyError:
    #     required dictionary key was missing
    #
    # TypeError:
    #     incorrect Python type
    #
    # ValueError:
    #     invalid value
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:

        # Convert the Python exception into an MCP error result.
        return _error_result(
            str(error)
        )

    # If the tool ran successfully, create a normal
    # successful MCP result.
    return types.CallToolResult(

        # Provide a JSON/text representation.
        content=[
            types.TextContent(
                type="text",
                text=json.dumps(
                    result,
                    separators=(",", ":"),
                ),
            )
        ],

        # Also provide the original structured dictionary.
        structuredContent=result,
    )


# START THE MCP SERVER USING STDIO

async def run_stdio() -> None:

    # Start the MCP stdio transport.
    #
    # This creates two streams:
    #
    #     read_stream
    #         client → server messages
    #
    #     write_stream
    #         server → client messages
    #
    # async with keeps the streams alive while the server
    # is running and closes them when the server exits.
    async with stdio_server() as (
        read_stream,
        write_stream,
    ):

        # Start the MCP server's event loop.
        #
        # MCP reads requests from read_stream,
        # dispatches them to registered handlers such as:
        #
        #     list_tools()
        #     call_tool()
        #
        # and writes responses through write_stream.
        await mcp.run(
            read_stream,
            write_stream,

            # Create the initialization settings/capabilities
            # that are used during the MCP handshake.
            mcp.create_initialization_options(),
        )


# APPLICATION ENTRY POINT

def main() -> None:

    # Start the asyncio event loop and run the MCP stdio server.
    #
    # run_stdio() is asynchronous, so asyncio.run()
    # is needed to execute it from normal synchronous Python code.
    asyncio.run(
        run_stdio()
    )

if __name__ == "__main__":

    main()
