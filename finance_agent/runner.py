from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_groq import ChatGroq
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
)

from config.settings import settings
from config.logger import logger

from finance_agent.errors import LLMProviderError, PostgresPersistenceError
from finance_agent.graph import build_finance_agent_graph
from finance_agent.tools import build_finance_tools


class FinanceAgentRunner:
    """Run LangGraph with native Python finance tools and optional Postgres persistence."""

    def __init__(
        self,
        *,
        chat_model: BaseChatModel | None = None,
        tools: Sequence[BaseTool] | None = None,
        database_url: str | None = None,
    ) -> None:
        self._chat_model = chat_model
        self._injected_tools = list(tools) if tools is not None else None
        self._database_url = database_url
        self._graph: CompiledStateGraph | None = None
        self._tools: list[BaseTool] | None = None
        self._checkpointer_cm: Any = None
        self._checkpointer: BaseCheckpointSaver | None = None

    @property
    def tools(self) -> list[BaseTool]:
        if self._tools is None:
            raise RuntimeError("Finance agent has not been started.")
        return self._tools

    @property
    def is_persistent(self) -> bool:
        return self._checkpointer is not None

    async def start(self) -> None:
        if self._graph is not None:
            return

        database_url = (
            settings.DATABASE_URL
            if self._database_url is None
            else self._database_url
        )

        if database_url:
            try:
                self._checkpointer_cm = AsyncPostgresSaver.from_conn_string(database_url)
                self._checkpointer = await self._checkpointer_cm.__aenter__()
                await self._checkpointer.setup()
            except Exception as exc:
                logger.exception(
                    "Failed to initialize PostgreSQL conversation persistence."
                )
                await self._close_checkpointer()
                raise PostgresPersistenceError(
                    "PostgreSQL conversation persistence could not be initialized. "
                    "Check DATABASE_URL and confirm that PostgreSQL is reachable."
                ) from exc

            logger.info("Conversation checkpointing enabled (Postgres).")
        else:
            logger.warning(
                "No DATABASE_URL configured; conversation state will not persist across restarts."
            )

        tools = (
            self._injected_tools
            if self._injected_tools is not None
            else build_finance_tools()
        )
        model = self._chat_model or _build_llm_chat_model()

        self._tools = list(tools)
        self._graph = build_finance_agent_graph(
            model,
            self._tools,
            checkpointer=self._checkpointer,
        )

        logger.info(
            "Finance agent graph is ready with %d native tools.",
            len(self._tools),
        )

    def _build_config(self, thread_id: str | None) -> dict[str, Any] | None:
        if self._checkpointer is None:
            return None
        if not thread_id:
            raise ValueError(
                "thread_id is required when conversation checkpointing is enabled."
            )
        return {"configurable": {"thread_id": thread_id}}

    async def ainvoke(
        self,
        messages: Sequence[Any] | str,
        *,
        thread_id: str | None = None,
    ) -> str:
        await self.start()
        if self._graph is None:
            raise RuntimeError("Finance agent graph was not compiled.")

        normalized_messages = (
            [{"role": "user", "content": messages}]
            if isinstance(messages, str)
            else messages
        )
        config = self._build_config(thread_id)

        if config is None:
            result = await self._graph.ainvoke(
                {"messages": _to_langchain_messages(normalized_messages)}
            )
        else:
            result = await self._graph.ainvoke(
                {"messages": _to_langchain_messages(normalized_messages)},
                config=config,
            )

        return _content_to_text(result["messages"][-1].content)

    async def astream_text(
        self,
        messages: Sequence[Any] | str,
        *,
        thread_id: str | None = None,
    ) -> AsyncIterator[str]:
        await self.start()
        if self._graph is None:
            raise RuntimeError("Finance agent graph was not compiled.")

        normalized_messages = (
            [{"role": "user", "content": messages}]
            if isinstance(messages, str)
            else messages
        )
        config = self._build_config(thread_id)
        payload = {"messages": _to_langchain_messages(normalized_messages)}

        if config is None:
            stream = self._graph.astream(
                payload,
                stream_mode="messages",
            )
        else:
            stream = self._graph.astream(
                payload,
                config=config,
                stream_mode="messages",
            )

        async for chunk, metadata in stream:
            if not isinstance(chunk, (AIMessage, AIMessageChunk)):
                continue
            if metadata.get("langgraph_node") != "call_model":
                continue

            text = _content_to_text(chunk.content)
            if text:
                yield text

    async def _close_checkpointer(self) -> None:
        if self._checkpointer_cm is None:
            self._checkpointer = None
            return

        try:
            await self._checkpointer_cm.__aexit__(None, None, None)
        except Exception:
            logger.exception("Failed to close PostgreSQL checkpointer cleanly.")
        finally:
            self._checkpointer_cm = None
            self._checkpointer = None

    async def stop(self) -> None:
        await self._close_checkpointer()
        self._graph = None
        self._tools = None


def _build_llm_chat_model() -> ChatGroq:
    try:
        return ChatGroq(
            groq_api_key=settings.GROQ_API_KEY,
            model_name=settings.GROQ_MODEL,
            temperature=0.0,
            # Voice replies are intentionally concise. Capping generation
            # prevents an unnecessarily large completion budget from adding
            # to Groq token usage.
            max_tokens=512,
        )
    except Exception as exc:
        logger.exception("Failed to initialize the Groq LLM.")
        raise LLMProviderError(
            "Groq LLM could not be initialized. "
            "Check GROQ_API_KEY and GROQ_MODEL."
        ) from exc


def _to_langchain_messages(messages: Sequence[Any]) -> list[BaseMessage]:
    converted: list[BaseMessage] = []

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
