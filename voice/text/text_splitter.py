import asyncio

from voice.text.events import SentenceEvent


class SentenceSplitter:

    SENTENCE_ENDINGS = (".", "!", "?")

    def __init__(
        self,
        sentence_queue: asyncio.Queue[SentenceEvent],
    ):
        self.sentence_queue = sentence_queue

        self._buffer = ""

    async def feed(self, text: str) -> None:

        self._buffer += text

        # Keep checking because one chunk can contain multiple sentences
        while True:

            # Find the position of the first sentence-ending character
            boundary_index = self._find_sentence_boundary()

            # No complete sentence yet; wait for more text
            if boundary_index == -1:
                return None

            # Extract the complete sentence from the buffer
            sentence = (
                self._buffer[:boundary_index + 1]
                .strip()
            )

            # Remove the extracted sentence from the buffer
            # and keep any remaining text for the next sentence
            self._buffer = (
                self._buffer[boundary_index + 1:]
            )

            # Ignore empty sentences
            if not sentence:
                continue

            await self.sentence_queue.put(
                SentenceEvent(text=sentence)
            )

    def _find_sentence_boundary(self) -> int:

        # Check every character in the buffer along with its index
        for index, character in enumerate(self._buffer):

            # Return the index when a sentence-ending character is found
            if character in self.SENTENCE_ENDINGS:
                return index

        # No sentence-ending character was found
        return -1

    async def flush(self) -> None:

        # Get any remaining text that hasn't ended with punctuation
        text = self._buffer.strip()

        # Clear the buffer because we're processing its remaining text
        self._buffer = ""

        # Nothing left to send
        if not text:
            return

        # Send the remaining text as a sentence
        await self.sentence_queue.put(
            SentenceEvent(text=text)
        )

    def clear(self) -> None:

        self._buffer = ""