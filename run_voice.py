import asyncio

from config.logger import logger
from finance_agent.persistence import close_pool, initialize_database
from voice.pipeline import VoicePipeline


async def main() -> None:
    pipeline = None

    try:
        # Ensure PostgreSQL tables exist before starting the agent.
        initialize_database()

        pipeline = VoicePipeline()
        await pipeline.start()

        logger.info(
            "ArthaVani is running. Press Ctrl+C to stop."
        )

        await asyncio.Event().wait()

    finally:
        try:
            if pipeline is not None:
                await pipeline.stop()
        finally:
            close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("ArthaVani stopped.")