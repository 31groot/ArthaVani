import asyncio
from collections.abc import AsyncGenerator

from elevenlabs import AsyncElevenLabs

from config.logger import logger
from config.settings import settings

class ElevenLabsTTS:

    def __init__(self):

        self.client = AsyncElevenLabs(
            api_key=settings.elevenlabs.api_key,
        )

    async def stream(
        self,
        text: str,
    ) -> AsyncGenerator[bytes, None]:

        if not text.strip():
            return

        logger.info("Starting ElevenLabs TTS stream.")

        try:

            audio_stream = self.client.text_to_speech.convert(
                voice_id=settings.elevenlabs.voice_id,
                text=text,
                model_id=settings.elevenlabs.model,
                output_format="pcm_16000",
            )

            async for audio_chunk in audio_stream:

                if not audio_chunk:
                    continue

                yield audio_chunk

        except asyncio.CancelledError:

            logger.info(
                "ElevenLabs TTS stream cancelled."
            )

            raise

        except Exception:

            logger.exception(
                "ElevenLabs TTS stream failed."
            )

            raise

        logger.info(
            "ElevenLabs TTS stream finished."
        )