from collections import deque

from config.constants import MAX_MESSAGES
from voice.memory.message import ChatMessage


class ConversationHistory:

    def __init__(
        self,
        max_messages: int = MAX_MESSAGES,
    ):

        # Store conversation messages in a deque (double-ended queue).
        #
        # maxlen limits how many messages can be stored.
        #
        # Example:
        #     max_messages = 10
        #
        # When the 11th message is added, the oldest message is
        # automatically removed.
        #
        # This prevents the conversation history from growing forever
        # and keeps the amount of context sent to the LLM bounded.
        self._messages: deque[ChatMessage] = deque(
            maxlen=max_messages,
        )

    def add_user(
        self,
        text: str,
    ) -> None:

        # Create a ChatMessage representing what the user said.
        message = ChatMessage(
            role="user",
            content=text,
        )

        # Add the user message to the conversation history.
        self._messages.append(
            message
        )

    def add_assistant(
        self,
        text: str,
    ) -> None:

        # Create a ChatMessage representing the assistant's response.
        message = ChatMessage(
            role="assistant",
            content=text,
        )

        # Add the assistant message to the conversation history.
        self._messages.append(
            message
        )

    def messages(
        self,
    ) -> list[ChatMessage]:

        # Return the conversation as a normal Python list.
        #
        # Internally we use deque so that maxlen can automatically
        # remove old messages, but callers don't need to know about
        # that implementation detail.
        return list(
            self._messages
        )

    def clear(
        self,
    ) -> None:

        # Remove every message from the conversation history.
        self._messages.clear()
