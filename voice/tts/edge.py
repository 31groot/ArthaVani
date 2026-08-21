import asyncio

import edge_tts

from config.logger import logger
from config.settings import settings


class EdgeTTS:

    def __init__(self):

        self.voice = settings.EDGE_TTS_VOICE

    async def stream(
        self,
        text: str,
    ):

        if not text.strip():
            return

        logger.info(
            "Starting Edge-TTS stream: voice=%s text=%r",
            self.voice,
            text,
        )

        process = None

        try:

            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-loglevel", "error",
                "-i", "pipe:0",
                "-f", "s16le",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "pipe:1",

                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
            )

            async def feed_ffmpeg():

                try:

                    async for chunk in communicate.stream():

                        if chunk["type"] != "audio":
                            continue

                        data = chunk["data"]

                        if not data:
                            continue

                        process.stdin.write(data)

                        await process.stdin.drain()

                    process.stdin.close()

                    try:
                        await process.stdin.wait_closed()
                    except AttributeError:
                        pass

                except asyncio.CancelledError:

                    raise

            feed_task = asyncio.create_task(
                feed_ffmpeg()
            )

            try:

                while True:

                    pcm = await process.stdout.read(
                        3200
                    )

                    if not pcm:
                        break

                    yield pcm

            finally:

                if not feed_task.done():

                    feed_task.cancel()

                    try:
                        await feed_task
                    except asyncio.CancelledError:
                        pass

        except asyncio.CancelledError:

            logger.info(
                "Edge-TTS stream cancelled."
            )

            raise

        except Exception:

            logger.exception(
                "Edge-TTS stream failed."
            )

            raise

        finally:

            if process is not None:

                if process.returncode is None:

                    process.kill()

                    try:
                        await process.wait()
                    except Exception:
                        pass

        logger.info(
            "Edge-TTS stream finished."
        )