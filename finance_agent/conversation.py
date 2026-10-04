from pydantic import BaseModel, ConfigDict


class ConversationIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str

    @property
    def thread_id(self) -> str:
        return self.user_id