import asyncio
import random
from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from config.logger import logger
from finance_agent.errors import LLMProviderError, LLMRateLimitError

from config.constants import RATE_LIMIT_MAX_ATTEMPTS, RATE_LIMIT_BASE_DELAY_SECONDS, MAX_HISTORY_TURNS


FINANCE_AGENT_SYSTEM_PROMPT = """
You are ArthaVani, a real-time AI voice assistant for personal finance and
market research.

Your responses are spoken aloud.
keep your answer summarized and short
For voice responses, output plain conversational text only.

Do not use Markdown or formatting characters.
Never use:
- **
- *
- #
- _
- backticks
- bullet markers such as "- " or "* "
- Markdown links
- tables

Use normal spoken sentences. Separate ideas with short sentences.
Do not output headings or lists.

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
def _is_rate_limit_error(exc: Exception) -> bool:
    """Best-effort detection of a rate/usage-limit rejection.

    Checks the HTTP status code where available and falls back to
    matching on the error body, rather than depending on one exception
    class from one provider's SDK.
    """
    status_code = getattr(exc, "status_code", None)
    if status_code not in (429, 413):
        return False

    message = str(exc).lower()
    return any(
        marker in message
        for marker in ("rate_limit", "rate limit", "tokens per minute", "tpm")
    )



# Keep the provider request comfortably below small/free-tier TPM caps.
# The exact token count varies by tokenizer, so we reduce the two biggest
# sources of prompt growth: unneeded tool schemas and old tool-call history.
MAX_HISTORY_TURNS = 3

TOOL_GROUPS = {
    "portfolio": {
        "get_portfolio_summary",
        "get_portfolio_risk",
    },
    "company": {
        "yahoo_get_quote",
        "yahoo_get_fundamentals",
        "yahoo_get_history",
        "yahoo_get_technical_analysis",
        "yahoo_get_news",
        "yahoo_get_corporate_actions",
        "yahoo_get_earnings_calendar",
    },
    "mutual_fund": {
        "amfi_get_latest_nav",
        "amfi_get_nav_history",
    },
    "currency": {
        "convert_currency",
    },
    "market_status": {
        "get_nse_market_status",
    },
    "watchlist": {
        "watchlist_add",
        "watchlist_remove",
        "watchlist_list",
        "watchlist_check",
    },
}

def _select_tools_for_turn(user_text: str, tools: Sequence[BaseTool]) -> list[BaseTool]:
    """Return only the tool schemas relevant to the current voice turn.

    Sending every finance tool schema on every request is expensive in tokens.
    A normal conversational question such as "How can you help me?" needs no
    finance tool definitions at all.
    """
    text = user_text.lower()
    selected_names: set[str] = set()

    portfolio_terms = (
        "portfolio",
        "holding",
        "holdings",
        "my investment",
        "my investments",
        "p&l",
        "pnl",
        "my profit",
        "my loss",
        "allocation of my",
        "concentration",
        "diversification",
        "portfolio risk",
    )
    if any(term in text for term in portfolio_terms):
        selected_names.update(TOOL_GROUPS["portfolio"])

    company_terms = (
        "stock",
        "share",
        "shares",
        "ticker",
        "price",
        "quote",
        "company",
        "fundamental",
        "valuation",
        "revenue",
        "earnings",
        "news",
        "technical",
        "rsi",
        "sma",
        "moving average",
        "historical",
        "history",
        "dividend",
        "dividends",
        "split",
        "splits",
    )
    if any(term in text for term in company_terms):
        selected_names.update(TOOL_GROUPS["company"])

    mutual_fund_terms = (
        "mutual fund",
        "mutual funds",
        "nav",
        "sip",
        "fund scheme",
    )
    if any(term in text for term in mutual_fund_terms):
        selected_names.update(TOOL_GROUPS["mutual_fund"])

    currency_terms = (
        "currency",
        "exchange rate",
        "fx",
        "convert",
        "usd",
        "inr",
        "eur",
        "gbp",
        "dollar",
        "rupee",
        "euro",
        "pound",
    )
    if any(term in text for term in currency_terms):
        selected_names.update(TOOL_GROUPS["currency"])

    market_status_terms = (
        "nse open",
        "nse closed",
        "market open",
        "market closed",
        "market status",
        "is the market open",
    )
    if any(term in text for term in market_status_terms):
        selected_names.update(TOOL_GROUPS["market_status"])

    watchlist_terms = (
        "watchlist",
        "price alert",
        "price alerts",
        "target price",
        "alert",
    )
    if any(term in text for term in watchlist_terms):
        selected_names.update(TOOL_GROUPS["watchlist"])

    return [tool for tool in tools if tool.name in selected_names]


def _recent_model_messages(
    state_messages: Sequence,
    *,
    max_turns: int = MAX_HISTORY_TURNS,
) -> list:
    """Keep current-turn tool context plus a small text-only conversation window.

    Old ToolMessages can be very large (for example historical price data).
    They are not useful enough to justify replaying them on every new turn.
    The current turn remains intact so the model can answer from fresh tool
    results.
    """
    human_indices = [
        index
        for index, message in enumerate(state_messages)
        if getattr(message, "type", None) == "human"
    ]

    if not human_indices:
        return list(state_messages)[-8:]

    current_start = human_indices[-1]
    prior_start = human_indices[-max_turns] if len(human_indices) >= max_turns else 0

    compact_prior = []
    for message in state_messages[prior_start:current_start]:
        message_type = getattr(message, "type", None)
        if message_type not in {"human", "ai"}:
            continue
        if getattr(message, "tool_calls", None):
            continue
        compact_prior.append(message)

    return compact_prior + list(state_messages[current_start:])


def _is_request_too_large(exc: Exception) -> bool:
    """True for deterministic oversized-request failures that should not retry."""
    status_code = getattr(exc, "status_code", None)
    message = str(exc).lower()
    return (
        status_code == 413
        or "request too large" in message
        or "requested" in message and "tokens per minute" in message
    )


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
    async def call_model(state: MessagesState) -> dict:
        # The system prompt is prepended here, at inference time, rather
        # than being passed in by the caller and persisted into checkpoint
        # state. With a checkpointer attached, `state["messages"]` already
        # contains prior conversation for this thread_id.
        user_text = ""
        for message in reversed(state["messages"]):
            if getattr(message, "type", None) == "human":
                user_text = str(getattr(message, "content", "") or "")
                break

        selected_tools = _select_tools_for_turn(user_text, tools)
        recent_messages = _recent_model_messages(state["messages"])
        messages = [SystemMessage(content=FINANCE_AGENT_SYSTEM_PROMPT)] + recent_messages

        # Bind only relevant tool schemas for this turn. This is the biggest
        # token saving for generic voice questions and keeps the request under
        # small TPM limits instead of sending all finance schemas every time.
        model_for_turn = model.bind_tools(selected_tools) if selected_tools else model

        logger.debug(
            "LLM context: %d messages, %d selected tools (%s).",
            len(messages),
            len(selected_tools),
            ", ".join(tool.name for tool in selected_tools) or "none",
        )

        provider_name = model.__class__.__name__
        last_rate_limit_exc: Exception | None = None

        for attempt in range(1, RATE_LIMIT_MAX_ATTEMPTS + 1):
            try:
                response = await model_for_turn.ainvoke(messages)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A 413/request-too-large response is deterministic for the
                # current payload. Retrying the exact same request cannot fix it.
                if (
                    _is_rate_limit_error(exc)
                    and not _is_request_too_large(exc)
                    and attempt < RATE_LIMIT_MAX_ATTEMPTS
                ):
                    last_rate_limit_exc = exc
                    # Exponential backoff with jitter, so a burst of
                    # concurrent sessions hitting the same limit don't all
                    # retry in lockstep.
                    delay = RATE_LIMIT_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                    delay += random.uniform(0, delay * 0.25)
                    logger.warning(
                        "%s rate-limited (attempt %d/%d); retrying in %.1fs.",
                        provider_name,
                        attempt,
                        RATE_LIMIT_MAX_ATTEMPTS,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.exception("%s LLM request failed.", provider_name)

                if _is_rate_limit_error(exc):
                    raise LLMRateLimitError(
                        f"{provider_name} is currently rate-limited "
                        "(request exceeded the provider's token/usage "
                        "limit) and retries were exhausted."
                    ) from exc

                raise LLMProviderError(
                    f"{provider_name} LLM request failed. "
                    "Check the model configuration, network connection, "
                    "and provider availability."
                ) from exc
            else:
                return {"messages": [response]}

        # Unreachable in practice: the loop above always either returns or
        # raises. Kept as a defensive guard in case RATE_LIMIT_MAX_ATTEMPTS
        # is ever set to 0.
        raise LLMRateLimitError(
            f"{provider_name} is currently rate-limited."
        ) from last_rate_limit_exc

    builder = StateGraph(MessagesState)
    builder.add_node("call_model", call_model)
    builder.add_node("tools", ToolNode(list(tools)))
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges("call_model", tools_condition)
    builder.add_edge("tools", "call_model")
    return builder.compile(checkpointer=checkpointer)