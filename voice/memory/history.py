from collections import deque

from voice.memory.message import ChatMessage

class ConversationHistory:

    def __init__(self,max_messages: int = 20,):

        self._messages: deque[ChatMessage] = deque(maxlen=max_messages,)

    def add_user(self, text: str,)-> None:

        self._messages.append(
            ChatMessage(
                role="user",
                content=text,
            )
        )

    def add_assistant(
        self,
        text: str,
    ) -> None:

        self._messages.append(
            ChatMessage(
                role="assistant",
                content=text,
            )
        )

    def messages(self) -> list[ChatMessage]:

        return list(self._messages)

    def clear(self):

        self._messages.clear()