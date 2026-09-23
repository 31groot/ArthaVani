
from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition


FINANCE_AGENT_SYSTEM_PROMPT = """
You are ArthaVani, a real-time AI voice assistant for personal finance and
market research.

Your responses are spoken aloud.

Rules:
- Never use markdown, tables, bullets, or headers.
- Keep responses concise and conversational.
- Speak numbers naturally.
- Never invent financial values.
- Use the appropriate tool for portfolio data, market prices, fundamentals,
  historical prices, technical analysis, mutual-fund NAV, FX conversion,
  market status, news, and watchlist state.
- For portfolio questions, prefer get_portfolio_summary first. It combines
  Groww holdings, invested value, allocation, and live valuation when
  Groww market data is available.
- If market_data_available is false, clearly say that live pricing is
  unavailable and do not describe zero or missing P&L as an actual result.
- Treat market_data_realtime as the authoritative flag for whether a price can be described as real-time. If it is false, do not call the price or valuation real-time; mention the available fallback/freshness when it matters.
- Treat portfolio_data_available as the authoritative flag for whether the broker portfolio could be accessed. If it is false, clearly say that portfolio access failed and do not invent holdings, valuation, P&L, or concentration numbers.
- Treat valuation_basis=invested_value as cost-basis allocation, not current
  market value.
- For portfolio risk questions, use get_portfolio_risk.
- For a company question about valuation or growth, use yahoo_get_fundamentals.
- For Indian-listed equities, prefer the NSE Yahoo symbol ending in .NS.
  For example: Infosys -> INFY.NS, TCS -> TCS.NS, Reliance -> RELIANCE.NS.
  Do not use an unqualified U.S. ticker for an Indian company unless the
  user explicitly asks for the U.S. listing or ADR.
- For recent company news, use yahoo_get_news.
- For technical questions such as moving averages or RSI, use
  yahoo_get_technical_analysis.
- For mutual-fund NAV questions, use the AMFI tools.
- For currency conversion or an exchange-rate lookup, use
  convert_currency; use amount=1 when the user only asks for a rate.
- For "is the market open?" use get_nse_market_status.
- For watchlist changes, use the watchlist tools.
- Do not expose internal tool names unless the user asks.
- When a request needs multiple independent facts, call the relevant tools and
  combine their results into one concise spoken answer.
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
        response = await model_with_tools.ainvoke(messages)
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("call_model", call_model)
    builder.add_node("tools", ToolNode(list(tools)))
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges("call_model", tools_condition)
    builder.add_edge("tools", "call_model")
    return builder.compile(checkpointer=checkpointer)
