import asyncio

from voice.text.events import SentenceEvent


class SentenceSplitter:

    # Characters that indicate the end of a sentence.
    SENTENCE_ENDINGS = (
        ".",
        "!",
        "?",
    )

    def __init__(
        self,
        sentence_queue: asyncio.Queue[SentenceEvent],
    ):

        # Queue where completed sentences are sent.
        self.sentence_queue = sentence_queue

        # Stores streamed LLM text that has not yet formed
        # a complete sentence.
        self._buffer = ""

    async def feed(
        self,
        text: str,
    ) -> None:

        # Add the newly received LLM text chunk to the buffer.
        self._buffer += text

        # Keep extracting sentences until no complete sentence remains.
        while True:

            boundary_index = self._find_sentence_boundary()

            if boundary_index == -1:
                return

            sentence = (
                self._buffer[
                    :boundary_index + 1
                ]
                .strip()
            )

            self._buffer = (
                self._buffer[
                    boundary_index + 1:
                ]
            )

            if not sentence:
                continue

            await self.sentence_queue.put(
                SentenceEvent(
                    text=sentence
                )
            )

    def _find_sentence_boundary(
        self,
    ) -> int:

        for index, character in enumerate(
            self._buffer
        ):

            if character not in self.SENTENCE_ENDINGS:
                continue

            # Decimal point inside a number:
            #
            #   0.9
            #   1.25
            #   1029.40
            #
            # This is not a sentence boundary.
            if character == "." and self._is_decimal_point(index):
                continue

            # If the period is currently the final character in the
            # streamed buffer and the previous character is a digit,
            # wait for the next chunk before deciding whether this is
            # a decimal point.
            #
            # Example:
            #
            #   chunk 1 -> "0."
            #   chunk 2 -> "9 percent."
            #
            # We must not emit "0." from chunk 1.
            if (
                character == "."
                and index == len(self._buffer) - 1
                and index > 0
                and self._buffer[index - 1].isdigit()
            ):
                return -1

            return index

        return -1

    def _is_decimal_point(
        self,
        index: int,
    ) -> bool:

        # A period is decimal punctuation when it sits between
        # two digits, for example:
        #
        #   0.9
        #   1.25
        #   1029.40

        if index <= 0 or index >= len(self._buffer) - 1:
            return False

        return (
            self._buffer[index - 1].isdigit()
            and self._buffer[index + 1].isdigit()
        )

    async def flush(
        self,
    ) -> None:

        # Handle anything remaining when the LLM finishes.
        text = self._buffer.strip()

        self._buffer = ""

        if not text:
            return

        await self.sentence_queue.put(
            SentenceEvent(
                text=text
            )
        )

    def clear(
        self,
    ) -> None:

        # Discard partially accumulated text.
        self._buffer = ""
