
import asyncio
from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from config.logger import logger
from finance_agent.errors import LLMProviderError

FINANCE_AGENT_SYSTEM_PROMPT = """
You are ArthaVani, a real-time AI voice assistant for personal finance and
market research.

Your responses are spoken aloud.
keep your answer summerised and short

Rules:
- Never use markdown, tables, bullets, or headers.
- Be concise, clear, and conversational.
- Speak numbers naturally, but financial accuracy always takes priority.
- Never invent, estimate, substitute, or change a financial value returned by a tool.
- Treat tool-returned financial values as authoritative.
- When stating a tool-returned number, preserve its value accurately; natural
  speech is allowed, but do not materially round or alter it.
- Before answering, verify every financial number in the response against the
  latest tool result.
- Never calculate or guess a financial value unless the required inputs are
  explicitly available from the tool results.
- Use the appropriate tool for portfolio data, market prices, fundamentals,
  historical prices, technical analysis, mutual-fund NAV, FX, market status,
  news, and watchlist state.
- For portfolio questions, use get_portfolio_summary first.
- For portfolio risk questions, use get_portfolio_risk.
- Questions about concentration, concentration HHI, largest holding weight,
  allocation concentration, or portfolio risk must use get_portfolio_risk;
  do not substitute get_portfolio_summary for these questions.
- Treat portfolio_data_available as authoritative. If false, clearly say that
  portfolio access failed and do not invent holdings, valuation, P&L, or risk data.
- Treat market_data_realtime as authoritative. If false, never describe prices
  or valuation as real-time.
- Treat valuation_basis as authoritative. If it is invested_value, describe
  allocation as cost-basis allocation, not market-value allocation.
- When market_data_available is false, clearly say that market pricing is
  unavailable and do not present missing or zero values as actual results.
- If fallback market data is used, clearly mention the fallback source when
  relevant.
- For company valuation or growth questions, use yahoo_get_fundamentals.
- For Indian-listed equities, prefer NSE symbols ending in .NS
  (for example INFY.NS, TCS.NS, RELIANCE.NS).
- Use yahoo_get_news for recent company news.
- Use yahoo_get_technical_analysis for technical indicators such as RSI or
  moving averages.
- Use the AMFI tools for mutual-fund NAV questions.
- Use convert_currency for currency conversion or exchange-rate questions.
  Use amount=1 when only a rate is requested.
- Use get_nse_market_status for questions about whether the NSE is open.
- Use the watchlist tools for watchlist changes or status.
- For requests requiring multiple independent facts, call the relevant tools
  and combine their results without changing their values.
- Do not expose internal tool names unless the user asks.
- Never claim real-time data unless the tool explicitly reports it as real-time.
- If a requested fact is unavailable, say so plainly rather than guessing.
"""
def build_finance_agent_graph(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build the finance agent graph.

    When `checkpointer` is provided (e.g. AsyncPostgresSaver), the graph
    persists its MessagesState after every step, keyed by the `thread_id`
    passed in each call's config. This lets a conversation resume across
    process restarts and keeps concurrent sessions correctly isolated.

    When `checkpointer` is None, the graph is stateless: each `ainvoke`/
    `astream` call only sees the messages explicitly passed to it.
    """
    model_with_tools = model.bind_tools(list(tools))

    async def call_model(state: MessagesState) -> dict:
        # The system prompt is prepended here, at inference time, rather
        # than being passed in by the caller and persisted into checkpoint
        # state. With a checkpointer attached, `state["messages"]` already
        # contains the full prior conversation for this thread_id, so
        # re-adding a SystemMessage on every turn would otherwise duplicate
        # it in Postgres on every single turn.
        messages = [SystemMessage(content=FINANCE_AGENT_SYSTEM_PROMPT)] + state["messages"]

        try:
            response = await model_with_tools.ainvoke(messages)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            provider_name = model.__class__.__name__
            logger.exception("%s LLM request failed.", provider_name)
            raise LLMProviderError(
                f"{provider_name} LLM request failed. "
                "Check the model configuration, network connection, "
                "and provider availability."
            ) from exc

        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("call_model", call_model)
    builder.add_node("tools", ToolNode(list(tools)))
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges("call_model", tools_condition)
    builder.add_edge("tools", "call_model")
    return builder.compile(checkpointer=checkpointer)
