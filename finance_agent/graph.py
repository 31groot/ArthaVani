from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

from langgraph.graph import (
    START,
    MessagesState,
    StateGraph,
)

from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import (
    ToolNode,
    tools_condition,
)


# System instructions for ArthaVani.

FINANCE_AGENT_SYSTEM_PROMPT = """
You are ArthaVani, a real-time AI voice assistant with access to personal-finance tools.

Your responses are converted directly to speech and read aloud, the person
never sees any text. This changes how you must format everything:

- NEVER use markdown: no tables, no pipe characters, no headers, no bullet
  points, no bold/italic asterisks. None of it will be read correctly aloud.
- NEVER read out every row of tabular data (e.g. every holding in a
  portfolio, every line item in a transaction list). Instead, summarize:
  mention the total, the 2-3 most significant items by value or change, and
  offer to go into more detail on a specific item if asked.
- Say numbers the way a person would say them in conversation (e.g. "two
  thousand four hundred eighty six Rupees and seventy five paise" or a
  natural shorthand like "about twenty four hundred eighty six Rupees" not "INR 2,486.75").
- Keep responses short: a few conversational sentences, not a report. 

Guidelines:
- Use tools for balances, transactions, spending, portfolio holdings, and stock quotes.
- Call multiple tools in one turn when the question needs more than one fact.
- After tools return, answer in natural spoken language following the rules above.
- Do not invent balances, transactions, or prices.
"""


def build_finance_agent_graph(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
) -> CompiledStateGraph:

    # Give the language model access to the finance tools.
    #
    # This does NOT execute the tools.
    #
    # It tells the model:
    #
    #     "Here are the tools you are allowed to request."
    
    model_with_tools = model.bind_tools(
        list(tools)
    )

    async def call_model(
        state: MessagesState,
    ) -> dict:

        # Send the current conversation to the LLM.
        #
        # The model may return either:
        #
        #     1. normal text
        #
        # or:
        #
        #     2. one or more tool calls
        #
        # ainvoke() is asynchronous so it doesn't block the
        # asyncio event loop while waiting for the model.
        response = await model_with_tools.ainvoke(
            state["messages"]
        )

        # Add the model's response to the graph's message state.
        
        # This could be:
        #
        #     AI text response
        # or:
        #     AI tool call(s)

        return {
            "messages": [response]
        }

    # Create a LangGraph state machine.
    # MessagesState provides the shared "messages" state that
    # flows through the graph.
    builder = StateGraph(
        MessagesState
    )

    # Add the LLM node.
    #
    # Whenever this node runs, call_model() is executed.
    builder.add_node(
        "call_model",
        call_model,
    )

    # Add the tools node.
  
    # ToolNode automatically executes the tool calls requested
    # by the LLM.
    builder.add_node(
        "tools",
        ToolNode(
            list(tools)
        ),
    )

    # The graph always begins by calling the model.
    #
    #     START → call_model
    builder.add_edge(
        START,
        "call_model",
    )

    # After the LLM responds, decide what happens next.
    #
    # tools_condition checks whether the latest AI message
    # contains tool calls.
    
    builder.add_conditional_edges(
        "call_model",
        tools_condition,
    )

    # After executing the tools, return to the model.
    #
    # This allows the LLM to see the tool results and produce
    # the final natural-language answer.
    #
    #     call_model
    #          ↓
    #        tools
    #          ↓
    #     call_model
    builder.add_edge(
        "tools",
        "call_model",
    )

    # Compile the graph into an executable LangGraph.
    return builder.compile()