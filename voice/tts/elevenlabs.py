import asyncio

from elevenlabs import AsyncElevenLabs

from config.logger import logger
from config.settings import settings


class ElevenLabsTTS:

    def __init__(self):

        self.client = AsyncElevenLabs(
            api_key=settings.ELEVENLABS_API_KEY,
        )

    async def stream(
        self,
        text: str,
    ):

        if not text.strip():
            return

        logger.info("Starting ElevenLabs TTS stream.")

        try:

            # This returns an async stream of audio chunks.
            audio_stream = self.client.text_to_speech.convert(
                voice_id=settings.ELEVENLABS_VOICE_ID,
                text=text,
                output_format="pcm_16000",
            )

            # Receive audio pieces as they become available
            async for audio_chunk in audio_stream:

                # Ignore empty audio chunks
                if not audio_chunk:
                    continue

                # Send each audio chunk immediately to the caller
                yield audio_chunk

        except asyncio.CancelledError:

            # Happens when the TTS operation is intentionally stopped
            logger.info(
                "ElevenLabs TTS stream cancelled."
            )

            raise

        except Exception:

            # Log unexpected errors and pass them to the caller
            logger.exception(
                "ElevenLabs TTS stream failed."
            )

            raise

        logger.info(
            "ElevenLabs TTS stream finished."
        )