from groq import AsyncGroq

from config.logger import logger
from config.settings import settings
from voice.llm.events import TokenEvent


class GroqLLM:

    def __init__(self):
        self.client = AsyncGroq(
            api_key=settings.GROQ_API_KEY,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
    ):

        if not messages:
            raise ValueError("messages cannot be empty.")

        logger.info("Sending request to Groq...")

        try:
            stream = await self.client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=messages,
                stream=True,
            )
        except Exception:
            logger.exception("Failed to start Groq stream.")
            raise

        try:
            async for chunk in stream:

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if delta is None:
                    continue

                token = delta.content

                if not token:
                    continue

                yield TokenEvent(text=token)

        except Exception:
            logger.exception("Groq stream interrupted.")
            raise

        logger.info("Groq stream finished.")