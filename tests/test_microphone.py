import asyncio

from voice.audio.microphone import Microphone


async def main():

    mic = Microphone()

    await mic.start()

    print("Speak...")

    for i in range(10):

        chunk = await mic.read()

        print(
            f"Chunk {i+1}",
            len(chunk),
            type(chunk),
        )

    await mic.stop()


if __name__ == "__main__":
    asyncio.run(main())