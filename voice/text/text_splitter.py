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

        while True:

            boundary_index = self._find_sentence_boundary()

            if boundary_index == -1:
                return

            sentence = (
                self._buffer[:boundary_index + 1]
                .strip()
            )

            self._buffer = (
                self._buffer[boundary_index + 1:]
            )

            if not sentence:
                continue

            await self.sentence_queue.put(
                SentenceEvent(text=sentence)
            )

    def _find_sentence_boundary(self) -> int:

        for index, character in enumerate(self._buffer):

            if character in self.SENTENCE_ENDINGS:
                return index

        return -1

    async def flush(self) -> None:

        text = self._buffer.strip()

        self._buffer = ""

        if not text:
            return

        await self.sentence_queue.put(
            SentenceEvent(text=text)
        )

    def clear(self) -> None:


        self._buffer = ""