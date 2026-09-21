import asyncio

from voice.text.events import SentenceEvent


class SentenceSplitter:

    # Characters that indicate the end of a sentence.
    #
    # When one of these characters is found, everything up to and
    # including that character is treated as one complete sentence.
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
        #
        # The TTS worker can read from this queue and start speaking
        # sentences as soon as they become available.
        self.sentence_queue = sentence_queue

        # Stores streamed LLM text that has not yet formed
        # a complete sentence.
        #
        # Example:
        #
        #   LLM sends: "Your current "
        #   buffer:    "Your current "
        #
        #   LLM sends: "balance?"
        #   buffer:    "Your current balance?"
        self._buffer = ""

    async def feed(
        self,
        text: str,
    ) -> None:

        # Add the newly received LLM text chunk to the existing buffer.
        #
        # The LLM may send text in very small pieces, so we need to
        # accumulate multiple chunks before a complete sentence exists.
        self._buffer += text

        # Keep extracting sentences until there is no complete
        # sentence left in the buffer.
        #
        # This is important because one LLM chunk may contain
        # multiple sentences.
        while True:

            # Search for the first '.', '!' or '?' in the buffer.
            boundary_index = (
                self._find_sentence_boundary()
            )

            # No sentence-ending character was found yet.
            #
            # Keep the current text in the buffer and wait for
            # another LLM chunk.
            if boundary_index == -1:
                return

            # Extract the sentence including the punctuation.
            #
            # +1 is necessary because Python slicing excludes
            # the end index.
            
            sentence = (
                self._buffer[
                    :boundary_index + 1
                ]
                .strip()
            )

            # Remove the sentence we just extracted from the buffer.
            #
            # Any text after the first sentence remains in the buffer.
            
            self._buffer = (
                self._buffer[
                    boundary_index + 1:
                ]
            )

            # Ignore empty sentences.
            if not sentence:
                continue

            # Send the completed sentence to the TTS queue.
            #
            # The TTS worker can now begin speaking this sentence
            # without waiting for the rest of the LLM response.
            await self.sentence_queue.put(
                SentenceEvent(
                    text=sentence
                )
            )

    def _find_sentence_boundary(
        self,
    ) -> int:

        # Examine every character in the current buffer.
        #
        # enumerate() gives us both:
        #
        #   index
        #   character
        #
        # Example:
        #
        #   "Hello."
        #
        #   0 H
        #   1 e
        #   2 l
        #   3 l
        #   4 o
        #   5 .
        for index, character in enumerate(
            self._buffer
        ):

            # Return the position of the first sentence-ending
            # character we encounter.
            if character in self.SENTENCE_ENDINGS:
                return index

        # No complete sentence exists yet.
        return -1

    async def flush(
        self,
    ) -> None:

        # Get whatever text is still waiting in the buffer.
        #
        # This handles cases where the LLM finishes without
        # ending the final sentence with punctuation.
        
        text = self._buffer.strip()

        # Clear the buffer because we are consuming its contents now.
        self._buffer = ""

        # Nothing remains to send.
        if not text:
            return

        # Treat the remaining text as a complete sentence and
        # send it to the TTS queue.
        await self.sentence_queue.put(
            SentenceEvent(
                text=text
            )
        )

    def clear(
        self,
    ) -> None:

        # Discard any partially accumulated sentence.
        #
        # This is useful when the user interrupts the assistant
        # and the current response should be abandoned.
        self._buffer = ""
