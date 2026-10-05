import asyncio

from config.logger import logger
from voice.pipeline import VoicePipeline


async def main() -> None:

    pipeline = VoicePipeline()

    try:

        await pipeline.start()

        logger.info(
            "ArthaVani is running. Press Ctrl+C to stop."
        )

        await asyncio.Event().wait()

    finally:

        await pipeline.stop()


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("ArthaVani stopped.")