from openai import AsyncAzureOpenAI

from config.logger import logger
from config.settings import settings
from voice.llm.events import TokenEvent
class AzureLLM:

    def __init__(self):
        self.client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        )


    async def stream(
        self,
        messages: list[dict[str, str]],
    ):

        if not messages:
            raise ValueError("messages cannot be empty.")

        logger.info("Sending request to Azure GPT...")

        try:
            stream = await self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT,
                messages=messages,
                stream=True,
            )
        except Exception:
            logger.exception("Failed to start Azure GPT stream.")
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
            logger.exception("Azure GPT stream interrupted.")
            raise

        logger.info("Azure GPT stream finished.")