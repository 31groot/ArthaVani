
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_groq import ChatGroq
from langgraph.graph.state import CompiledStateGraph

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from config.settings import settings
from config.logger import logger

from finance_agent.graph import build_finance_agent_graph, FINANCE_AGENT_SYSTEM_PROMPT
from finance_agent.tools import build_finance_tools


class FinanceAgentRunner:
    """Run LangGraph with native Python finance tools."""

    def __init__(
        self,
        *,
        chat_model: BaseChatModel | None = None,
        tools: Sequence[BaseTool] | None = None,
    ) -> None:
        self._chat_model = chat_model
        self._injected_tools = list(tools) if tools is not None else None
        self._graph: CompiledStateGraph | None = None
        self._tools: list[BaseTool] | None = None

    @property
    def tools(self) -> list[BaseTool]:
        if self._tools is None:
            raise RuntimeError("Finance agent has not been started.")
        return self._tools

    async def start(self) -> None:
        if self._graph is not None:
            return

        tools = (
            self._injected_tools
            if self._injected_tools is not None
            else build_finance_tools()
        )
        model = self._chat_model or _build_llm_chat_model()

        self._tools = list(tools)
        self._graph = build_finance_agent_graph(model, self._tools)

        logger.info(
            "Finance agent graph is ready with %d native tools.",
            len(self._tools),
        )

    async def ainvoke(self, messages: Sequence[Any] | str) -> str:
        await self.start()
        if self._graph is None:
            raise RuntimeError("Finance agent graph was not compiled.")

        normalized_messages = (
            [{"role": "user", "content": messages}]
            if isinstance(messages, str)
            else messages
        )

        result = await self._graph.ainvoke(
            {"messages": _to_langchain_messages(normalized_messages)}
        )
        return _content_to_text(result["messages"][-1].content)

    async def astream_text(
        self,
        messages: Sequence[Any] | str,
    ) -> AsyncIterator[str]:
        await self.start()
        if self._graph is None:
            raise RuntimeError("Finance agent graph was not compiled.")

        normalized_messages = (
            [{"role": "user", "content": messages}]
            if isinstance(messages, str)
            else messages
        )

        async for chunk, metadata in self._graph.astream(
            {"messages": _to_langchain_messages(normalized_messages)},
            stream_mode="messages",
        ):
            if not isinstance(chunk, (AIMessage, AIMessageChunk)):
                continue
            if metadata.get("langgraph_node") != "call_model":
                continue

            text = _content_to_text(chunk.content)
            if text:
                yield text

    async def stop(self) -> None:
        self._graph = None
        self._tools = None


def _build_llm_chat_model() -> ChatGroq:
    return ChatGroq(
        groq_api_key=settings.GROQ_API_KEY,
        model_name=settings.GROQ_MODEL,
        temperature=0.0,
    )


def _to_langchain_messages(messages: Sequence[Any]) -> list[BaseMessage]:
    converted: list[BaseMessage] = [
        SystemMessage(content=FINANCE_AGENT_SYSTEM_PROMPT)
    ]

    for message in messages:
        if isinstance(message, dict):
            role = message["role"]
            content = message["content"]
        else:
            role = message.role
            content = message.content

        if role == "system":
            continue
        if role == "user":
            converted.append(HumanMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            raise ValueError(f"Unsupported chat role '{role}'.")

    return converted


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)
