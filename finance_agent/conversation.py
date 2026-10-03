from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConversationIdentity:
    user_id: str

    def __post_init__(self) -> None:
        user_id = self.user_id.strip()

        if not user_id:
            raise ValueError("user_id must not be empty.")

        object.__setattr__(self, "user_id", user_id)

    @property
    def thread_id(self) -> str:
        return self.user_id
