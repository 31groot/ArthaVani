from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_groq import ChatGroq

# If the LLM provider is Azure OpenAI instead of Groq,

# from langchain_openai import AzureChatOpenAI


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

from finance_agent.graph import (
    build_finance_agent_graph,
    FINANCE_AGENT_SYSTEM_PROMPT,
)

from finance_agent.mcp_client import PersonalFinanceMCPClient


class FinanceAgentRunner:


    def __init__(
        self,
        *,
        chat_model: BaseChatModel | None = None,
        mcp_client: PersonalFinanceMCPClient | None = None,
        tools: Sequence[BaseTool] | None = None,
    ) -> None:

        # Optional LLM provided by the caller.
        # If this is None, start() will create the default
        self._chat_model = chat_model

        # MCP client provided by the caller.
        # If this is None, start() will create a
        # PersonalFinanceMCPClient automatically.
        self._mcp_client = mcp_client

        #Tools provided directly by the caller.
        #
        # This is useful for testing or for bypassing MCP.

        self._injected_tools = (
            list(tools)
            if tools is not None
            else None
        )

        # Decide whether this runner owns the MCP client.

        self._owns_mcp_client = (
            mcp_client is None
            and tools is None
        )

        # Compiled LangGraph agent.
        
        # None means the agent has not been started yet.
        self._graph: CompiledStateGraph | None = None

        # Tools actually being used by the graph.
        #
        # None means start() has not completed yet.
        self._tools: list[BaseTool] | None = None

    @property
    def tools(self) -> list[BaseTool]:

        # Prevent callers from accessing tools before
        # the agent has been started.

        if self._tools is None:
            raise RuntimeError(
                "Finance agent has not been started."
            )

        # Return the tools currently used by the agent.
        return self._tools

    async def start(self) -> None:

        # If the graph already exists, the agent has already
        # been started.
        #
        # This makes start() safe to call multiple times.
        if self._graph is not None:
            return

        # Start with any tools that were directly injected.

        tools = self._injected_tools

        # If no tools were injected, we need to obtain them
        # from the MCP server.
        if tools is None:

            # Use the MCP client supplied by the caller.
            #
            # If no client was supplied, create a default
            # PersonalFinanceMCPClient.
            client = (
                self._mcp_client
                or PersonalFinanceMCPClient()
            )

            # Store the client so stop() can close it later
            # when this runner owns it.
            self._mcp_client = client

            # Start the MCP server and establish the MCP session.
            await client.connect()

            # Ask the MCP server for its available tools.
            
            tools = await client.discover_tools()

        # Use the caller-provided chat model if available.
        #
        # Otherwise create the default model configured in
        # the application settings.
        model = (
            self._chat_model
            or _build_llm_chat_model()
        )

        # Store the final list of tools used by the graph.
        self._tools = list(tools)

        # Build and compile the LangGraph finance agent.
        #
        # The graph receives:
        #
        #     model
        #     tools
        #
        # and creates the model → tool → model workflow.
        self._graph = build_finance_agent_graph(
            model,
            self._tools,
        )

        logger.info(
            "Finance agent graph is ready with %d MCP tools.",
            len(self._tools),
        )

    async def ainvoke(
        self,
        messages: Sequence[Any],
    ) -> str:

        # Make sure the graph, model, and tools are ready.

        await self.start()

        # This check is mainly for type-safety and defensive
        # programming.
        #
        # start() should have created the graph above.
        if self._graph is None:
            raise RuntimeError(
                "Finance agent graph was not compiled."
            )

        # Convert the application's messages into the
        # LangChain message objects expected by LangGraph.
        
        result = await self._graph.ainvoke(
            {
                "messages": _to_langchain_messages(
                    messages
                )
            }
        )

        # LangGraph returns a state containing the message history.
        #
        # The last message is expected to be the final assistant
        # response after all required tool calls have completed.
        #
        # _content_to_text() converts LangChain's possible content
        # formats into one plain string for the voice pipeline.
        return _content_to_text(
            result["messages"][-1].content
        )

    async def astream_text(
        self,
        messages: Sequence[Any],
    ) -> AsyncIterator[str]:

        """
        Stream only assistant text produced by the model.

        Tool calls and tool results are intentionally hidden from
        the voice pipeline.

        Instead of waiting for the entire model response, this
        method yields text as it becomes available."

        The TTS pipeline can therefore start speaking before
        the complete response is finished.
        """

        # Make sure the graph is initialized before streaming.
        await self.start()

        # Defensive check to make sure the graph exists.
        if self._graph is None:
            raise RuntimeError(
                "Finance agent graph was not compiled."
            )

        # Convert the application's messages into LangChain
        # message objects and create the input state expected
        # by LangGraph.
        input_messages = {
            "messages": _to_langchain_messages(
                messages
            ),
        }

        # Stream LangGraph messages as they are produced.
        #
        # stream_mode="messages" tells LangGraph to provide
        # message-level streaming events.
        #
        # Each iteration gives us:
        #
        #     chunk
        #     metadata
        #
        # chunk:
        #     The actual message/message chunk.
        #
        # metadata:
        #     Information about where the chunk came from,
        #     such as the LangGraph node name.
        async for chunk, metadata in self._graph.astream(
            input_messages,
            stream_mode="messages",
        ):

            # We only care about AI messages.
            #
            # Other message types may appear in the stream,
            # especially when tools are involved.
            if not isinstance(
                chunk,
                (AIMessage, AIMessageChunk),
            ):
                continue

            # Find out which LangGraph node produced this message.
            #
            # In this graph:
            #
            #     "call_model"
            #
            # is the LLM node.
            node_name = metadata.get(
                "langgraph_node"
            )

            # Ignore AI messages that are not coming from
            # the model node we want to expose to the voice
            # pipeline.
            #
            # This helps prevent tool-related internal events
            # from being spoken aloud.
            if node_name != "call_model":
                continue

            # Convert the message content into plain text.
            text = _content_to_text(
                chunk.content
            )

            # Only yield non-empty text.
            if text:
                yield text

    async def stop(self) -> None:

        # Remove the compiled graph reference.
        #
        # This puts the runner back into an unstarted state.
        self._graph = None

        # Remove the current tool list as well.
        self._tools = None

        # Only close the MCP client if this runner created/owns it.
        #
        # If the caller supplied its own MCP client or tools,
        # this runner must not shut down resources that belong
        # to the caller.
        if (
            self._owns_mcp_client
            and self._mcp_client is not None
        ):

            # Close the MCP session, stdio streams,
            # and MCP server process.
            await self._mcp_client.aclose()

            # Remove our reference to the client.
            self._mcp_client = None


def _build_llm_chat_model() -> ChatGroq:

    # Create the default Groq chat model using values
    # loaded from the application settings.
    #
    # GROQ_API_KEY:
    #     Authentication key for Groq.
    #
    # GROQ_MODEL:
    #     Which Groq-hosted model to use.
    #
    # temperature=0.0:
    #     Makes the model behavior more deterministic.

    return ChatGroq(
        groq_api_key=settings.GROQ_API_KEY,
        model_name=settings.GROQ_MODEL,
        temperature=0.0,
    )



# Azure OpenAI alternative

# If the project uses Azure OpenAI instead of Groq, the model
# creation above could be replaced with AzureChatOpenAI.
#
# Example:
#
# from langchain_openai import AzureChatOpenAI
#
# return AzureChatOpenAI(
#     azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
#     api_key=settings.AZURE_OPENAI_API_KEY,
#     api_version=settings.AZURE_OPENAI_API_VERSION,
#     azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT,
# )


def _to_langchain_messages(
    messages: Sequence[Any],
) -> list[BaseMessage]:

    # Start the message list with the finance agent's
    # system prompt.
    #
    # The system prompt tells the model how it should behave
    # as a personal finance voice assistant.
    converted: list[BaseMessage] = [
        SystemMessage(
            content=FINANCE_AGENT_SYSTEM_PROMPT
        )
    ]

    # Convert each application-level message into the
    # appropriate LangChain message object.
    for message in messages:

        if isinstance(message, dict):

            role = message["role"]
            content = message["content"]

        else:

            role = message.role
            content = message.content

        # We already add our own finance system prompt above.
        #
        # Therefore, ignore any system messages supplied by
        # the caller instead of adding multiple system prompts.
        if role == "system":
            continue

        # Convert user messages into HumanMessage objects.
        if role == "user":

            converted.append(
                HumanMessage(
                    content=content
                )
            )

        # Convert assistant messages into AIMessage objects.
        elif role == "assistant":

            converted.append(
                AIMessage(
                    content=content
                )
            )

        # Reject roles that this adapter does not understand.
        #
        # This prevents silently passing malformed conversation
        # history into LangGraph.
        else:

            raise ValueError(
                f"Unsupported chat role '{role}'."
            )

    # Return the final LangChain-compatible conversation.
    return converted


def _content_to_text(
    content: Any,
) -> str:

    # No content means there is nothing to speak or return.
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    # LangChain can sometimes represent message content
    # as a list of content blocks.
    #
    # Example:
    #
    #     [
    #         {"type": "text", "text": "You spent "},
    #         {"type": "text", "text": "500"},
    #     ]
    #
    # We need to combine those blocks into one string.
    if isinstance(content, list):

        parts: list[str] = []

        for block in content:

            # A plain string block can be used directly.
            if isinstance(block, str):

                parts.append(block)

            # For structured blocks, only collect text blocks.
            #
            # Other block types, such as images or other
            # structured content, are intentionally ignored
            # because this function is specifically preparing
            # text for the voice pipeline.
            elif (
                isinstance(block, dict)
                and block.get("type") == "text"
            ):

                parts.append(
                    str(
                        block.get(
                            "text",
                            "",
                        )
                    )
                )

        # Join all extracted text blocks together.
        return "".join(parts)

    # Final fallback:
    #
    # If some unexpected content type reaches this function,
    # convert it to a string rather than crashing.
    return str(content)