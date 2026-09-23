from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConversationIdentity:
    user_id: str
    conversation_id: str = "default"

    def __post_init__(self) -> None:
        user_id = self.user_id.strip()
        conversation_id = self.conversation_id.strip()

        if not user_id:
            raise ValueError("user_id must not be empty.")
        if not conversation_id:
            raise ValueError("conversation_id must not be empty.")

        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "conversation_id", conversation_id)

    @property
    def thread_id(self) -> str:
        return f"user:{self.user_id}:conversation:{self.conversation_id}"
