import os
import uuid
import unittest
from unittest.mock import patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import StructuredTool
from pydantic import Field

from finance_agent.errors import PostgresPersistenceError
from finance_agent.graph import build_finance_agent_graph
from finance_agent.runner import FinanceAgentRunner


class ContextAwareChatModel(BaseChatModel):
    seen_messages: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "context-aware-test-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen_messages.append(list(messages))
        last_user = [m for m in messages if isinstance(m, HumanMessage)][-1]
        prior = any(
            isinstance(m, HumanMessage) and "blue" in str(m.content).lower()
            for m in messages[:-1]
        )
        if "what color" in str(last_user.content).lower():
            content = "You told me blue." if prior else "I do not have that context."
        else:
            content = "Okay, I will remember that."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


def _empty_tools() -> list[StructuredTool]:
    return []


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_thread_preserves_messages_with_memory_checkpointer(self):
        model = ContextAwareChatModel()
        graph = build_finance_agent_graph(
            model,
            _empty_tools(),
            checkpointer=MemorySaver(),
        )

        config = {"configurable": {"thread_id": "memory-test"}}

        first = await graph.ainvoke(
            {"messages": [HumanMessage(content="My favorite color is blue.")]},
            config=config,
        )
        self.assertEqual(
            first["messages"][-1].content,
            "Okay, I will remember that.",
        )

        second = await graph.ainvoke(
            {"messages": [HumanMessage(content="What color did I tell you?")]},
            config=config,
        )
        self.assertEqual(
            second["messages"][-1].content,
            "You told me blue.",
        )

    async def test_postgres_startup_failure_raises_clear_error(self):
        class FailingCheckpointer:
            async def __aenter__(self):
                raise ConnectionError("connection refused")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        runner = FinanceAgentRunner(
            chat_model=ContextAwareChatModel(),
            tools=[],
            database_url="postgresql://invalid",
        )

        with patch(
            "finance_agent.runner.AsyncPostgresSaver.from_conn_string",
            return_value=FailingCheckpointer(),
        ):
            with self.assertRaises(PostgresPersistenceError) as context:
                await runner.start()

        self.assertIn(
            "PostgreSQL conversation persistence could not be initialized",
            str(context.exception),
        )
        self.assertFalse(runner.is_persistent)
        await runner.stop()


    async def test_build_config_requires_thread_id_for_persistence(self):
        runner = FinanceAgentRunner()
        runner._checkpointer = object()

        with self.assertRaises(ValueError):
            runner._build_config(None)

        self.assertEqual(
            runner._build_config("user-123"),
            {"configurable": {"thread_id": "user-123"}},
        )


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="Set DATABASE_URL to run the PostgreSQL integration test.",
)
@pytest.mark.asyncio
async def test_postgres_survives_runner_restart():
    database_url = os.environ["DATABASE_URL"]
    thread_id = f"pytest-{uuid.uuid4()}"

    first_model = ContextAwareChatModel()
    first_runner = FinanceAgentRunner(
        chat_model=first_model,
        tools=[],
        database_url=database_url,
    )
    try:
        first = await first_runner.ainvoke(
            "My favorite color is blue.",
            thread_id=thread_id,
        )
        assert first == "Okay, I will remember that."
    finally:
        await first_runner.stop()

    second_model = ContextAwareChatModel()
    second_runner = FinanceAgentRunner(
        chat_model=second_model,
        tools=[],
        database_url=database_url,
    )
    try:
        second = await second_runner.ainvoke(
            "What color did I tell you?",
            thread_id=thread_id,
        )
        assert second == "You told me blue."
    finally:
        await second_runner.stop()
