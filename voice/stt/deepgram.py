import asyncio
import time

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types import (
    ListenV1Results,
    ListenV1UtteranceEnd,
)

from config.constants import SAMPLE_RATE
from config.logger import logger
from config.settings import settings

from voice.stt.events import TranscriptEvent


# Target amount of audio to send to Deepgram at once.
#
# Audio format:
#   - SAMPLE_RATE samples/second
#   - int16 = 2 bytes/sample
#   - mono = 1 channel
#
# Example with 16 kHz:
#
#   16000 samples/sec
#   × 2 bytes/sample
#   × 0.1 sec
#   = 3200 bytes
#
# So we batch microphone audio into approximately 100 ms
# chunks before sending it over the WebSocket.
SEND_CHUNK_BYTES = int(
    SAMPLE_RATE * 2 * 0.1
)


class DeepgramClient:

    def __init__(self):

        # Create the asynchronous Deepgram API client.
        self.client = AsyncDeepgramClient(
            api_key=settings.DEEPGRAM_API_KEY,
        )

        # Background task tracking delayed finalization for UtteranceEnd.
        self._utterance_end_task: asyncio.Task | None = None

        # Will contain the active Deepgram connection after connect().
        #
        # None means that we're not currently connected.
        self.connection = None

        # Reference to the asyncio event loop.
        #
        # Used by callback functions to safely put transcript
        # events onto the asyncio queue.
        self.loop: asyncio.AbstractEventLoop | None = None

        # Queue containing TranscriptEvent objects.
        #
        # Deepgram callbacks put events here.
        # LLMWorker later reads them using receive().
        self._events: asyncio.Queue[
            TranscriptEvent
        ] = asyncio.Queue()

        # Stores the asynchronous connection context.
        #
        # We manually enter it during connect()
        # and manually exit it during close().
        self._connection_context = None

        # Background task responsible for listening to
        # incoming Deepgram WebSocket events.
        self._listen_task: asyncio.Task | None = None

        # Stores the most recent transcript received from Deepgram.
        #
        # Example progression while the user speaks:
        #
        #   "what"
        #   "what is"
        #   "what is my"
        #   "what is my balance"
        #
        # _last_interim always points to the latest candidate.
        # Accumulated transcript for the current speaking turn.
        # Deepgram can split one utterance into multiple final segments.
        self._final_transcript = ""

        # Stores the latest non-final transcript candidate.
        self._last_interim: TranscriptEvent | None = None

        # Confidence of the most recent is_final segment.
        self._last_final_confidence = 0.0

        # Tracks whether the current speech turn has already
        # been finalized.
        #
        # True  = no active unfinalized speech turn
        # False = currently waiting to determine when the user stops
        self._turn_finalized = True

        # Monotonic timestamp of the latest interim transcript.
        #
        # Used by force_finalize() as a safety timeout.
        self._last_interim_time = 0.0

        # Temporary buffer used to collect small microphone
        # chunks until we have enough data for approximately
        # one 100 ms Deepgram frame.
        self._send_buffer = bytearray()

    async def connect(self) -> None:

        logger.info(
            "Connecting to Deepgram..."
        )

        # Save the currently running asyncio event loop.
        self.loop = asyncio.get_running_loop()

        # Create the Deepgram streaming connection configuration.
        #
        # encoding:
        #     The microphone sends 16-bit PCM audio.
        #
        # sample_rate:
        #     Must match the actual microphone audio.
        #
        # channels:
        #     Mono microphone audio.
        #
        # interim_results:
        #     Receive partial transcripts while the user is speaking.
        #
        # smart_format:
        #     Improve formatting of recognized text.
        #
        # punctuate:
        #     Add punctuation to transcripts.
        #
        # endpointing:
        #     Helps detect pauses/endpoints.
        #
        # utterance_end_ms:
        #     Deepgram's utterance-end timing.
        #
        # vad_events:
        #     Enable voice activity-related events.
        self._connection_context = (
            self.client.listen.v1.connect(
                model=settings.DEEPGRAM_MODEL,
                encoding="linear16",
                sample_rate=SAMPLE_RATE,
                channels=1,
                interim_results=True,
                smart_format=True,
                punctuate=True,
                endpointing=300,
                utterance_end_ms=1000,
                vad_events=True,
            )
        )

        # Enter the asynchronous connection context
        # and get the active Deepgram connection object.
        self.connection = (
            await self._connection_context.__aenter__()
        )

        # Log when Deepgram successfully opens the connection.
        self.connection.on(
            EventType.OPEN,
            lambda _: logger.info(
                "Deepgram connection opened."
            ),
        )

        # Log Deepgram errors.
        self.connection.on(
            EventType.ERROR,
            lambda error: logger.error(
                f"Deepgram error: {error}"
            ),
        )

        # Handle all incoming Deepgram messages.
        #
        # _on_message() decides whether the message is:
        #
        #   - a transcript result
        #   - an utterance-end event
        #   - something we don't care about
        self.connection.on(
            EventType.MESSAGE,
            self._on_message,
        )

        # Start the background task that listens for Deepgram events.
        self._listen_task = asyncio.create_task(
            self.connection.start_listening()
        )

        logger.info(
            "Deepgram connected."
        )

    async def send_audio(
        self,
        audio: bytes,
    ) -> None:

        # Don't allow audio to be sent before connect().
        if self.connection is None:
            raise RuntimeError(
                "Deepgram client is not connected."
            )

        # Add the new microphone bytes to our batching buffer.
        #
        # Microphone callbacks can produce small chunks, so we don't
        # immediately send every tiny chunk over the WebSocket.
        self._send_buffer.extend(
            audio
        )

        # Keep sending complete ~100 ms frames while the buffer
        # contains enough audio.
        while len(self._send_buffer) >= SEND_CHUNK_BYTES:

            # Take exactly one target-sized chunk.
            frame = bytes(
                self._send_buffer[
                    :SEND_CHUNK_BYTES
                ]
            )

            # Remove the chunk that we're about to send.
            #
            # Any leftover bytes remain in _send_buffer for the
            # next call to send_audio().
            del self._send_buffer[
                :SEND_CHUNK_BYTES
            ]

            # Send the audio frame to Deepgram.
            await self.connection.send_media(
                frame
            )

    async def receive(
        self,
    ) -> TranscriptEvent:

        # Wait for and return the next transcript event.
        #
        # The caller does not need to know that an asyncio.Queue
        # is being used internally.
        return await self._events.get()

    async def close(
        self,
    ) -> None:

        logger.info(
            "Closing Deepgram connection..."
        )

        # Stop the background listener task.
        if self._listen_task is not None:

            self._listen_task.cancel()

            try:

                # Wait for the listener task to finish cancellation.
                await self._listen_task

            except asyncio.CancelledError:

                # Cancellation during shutdown is expected.
                pass

            self._listen_task = None

        if (
            self._utterance_end_task is not None
            and not self._utterance_end_task.done()
        ):
            self._utterance_end_task.cancel()

            try:
                await self._utterance_end_task
            except asyncio.CancelledError:
                pass

            self._utterance_end_task = None

        # Exit the Deepgram connection context.
        if self._connection_context is not None:

            try:

                await self._connection_context.__aexit__(
                    None,
                    None,
                    None,
                )

            finally:

                # Reset connection state after shutdown.
                self._connection_context = None
                self.connection = None

        # Clear any unsent bytes that may still remain in the
        # local batching buffer.
        self._send_buffer.clear()

        logger.info(
            "Deepgram connection closed."
        )

    def _on_message(
        self,
        message,
    ) -> None:

        if isinstance(message, ListenV1UtteranceEnd):
            self._on_utterance_end()
            return

        if not isinstance(message, ListenV1Results):
            return

        alternatives = message.channel.alternatives
        transcript = alternatives[0].transcript if alternatives else ""
        confidence = alternatives[0].confidence if alternatives else 0.0

        if not transcript:
            return

        logger.info(
            "STT interim: text=%r confidence=%.3f is_final=%s speech_final=%s",
            transcript,
            confidence,
            message.is_final,
            message.speech_final,
        )

        # Deepgram's is_final finalizes a transcript segment, not
        # necessarily the entire user turn.
        if message.is_final:
            if (
                self._utterance_end_task is not None
                and not self._utterance_end_task.done()
            ):
                self._utterance_end_task.cancel()
                self._utterance_end_task = None

            self._final_transcript = self._merge_transcripts(
                self._final_transcript,
                transcript,
            )

            # Keep the latest interim candidate. It may contain words that
            # Deepgram has not yet included in the finalized segment.
            self._last_final_confidence = confidence
            self._turn_finalized = False
            self._last_interim_time = time.monotonic()

            # speech_final means this is the end of the speaking turn.
            if message.speech_final:
                self._emit_final_turn(confidence)
            return

        # Keep the latest interim candidate for UtteranceEnd / safety
        # finalization. Do not send interim text to the LLM queue.
        self._last_interim = TranscriptEvent(
            text=transcript,
            confidence=confidence,
            is_final=False,
            speech_final=False,
        )
        self._turn_finalized = False
        self._last_interim_time = time.monotonic()

    def _schedule_delayed_finalize(self) -> None:
        if (
            self._utterance_end_task is not None
            and not self._utterance_end_task.done()
        ):
            return

        self._utterance_end_task = asyncio.create_task(
            self._delayed_utterance_finalize()
        )

    def _on_utterance_end(
        self,
    ) -> None:

        if self._turn_finalized:
            return

        if not self._final_transcript and self._last_interim is None:
            return

        # Give any final transcript segment that is already in flight a
        # small amount of time to arrive before we close the turn.
        if (
            self._utterance_end_task is not None
            and not self._utterance_end_task.done()
        ):
            return

        # Safely schedule the task in the event loop if callback is invoked
        # from a background worker thread.
        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(self._schedule_delayed_finalize)
        else:
            self._schedule_delayed_finalize()

    async def _delayed_utterance_finalize(
        self,
    ) -> None:

        try:
            # Brief pause to allow any in-flight final segment to arrive
            await asyncio.sleep(0.75)

            if self._turn_finalized:
                return

            confidence = (
                self._last_interim.confidence
                if self._last_interim is not None
                else self._last_final_confidence
            )

            self._emit_final_turn(confidence)

        except asyncio.CancelledError:
            raise

        finally:
            self._utterance_end_task = None

    def _emit_final_turn(
        self,
        confidence: float,
    ) -> None:

        transcript = self._select_final_transcript(
            self._final_transcript,
            self._last_interim.text if self._last_interim is not None else "",
        )

        transcript = transcript.strip()

        if not transcript:
            return

        logger.info(
            "STT final: text=%r confidence=%.3f",
            transcript,
            confidence,
        )

        final_event = TranscriptEvent(
            text=transcript,
            confidence=confidence,
            is_final=True,
            speech_final=True,
        )

        self._turn_finalized = True
        self._last_interim = None
        self._final_transcript = ""
        self._last_final_confidence = 0.0
        self._last_interim_time = 0.0

        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(
                self._events.put_nowait,
                final_event,
            )

    @staticmethod
    def _select_final_transcript(
        finalized: str,
        interim: str,
    ) -> str:

        finalized = " ".join(finalized.split()).strip()
        interim = " ".join(interim.split()).strip()

        if not finalized:
            return interim

        if not interim:
            return finalized

        finalized_lower = finalized.casefold()
        interim_lower = interim.casefold()

        # A newer interim can be a longer cumulative hypothesis.
        if interim_lower.startswith(finalized_lower):
            return interim

        # Otherwise keep the finalized result. Never concatenate competing
        # hypotheses, because that can produce duplicated text.
        return finalized

    @staticmethod
    def _merge_transcripts(
        base: str,
        update: str,
    ) -> str:
        base = " ".join(base.split()).strip()
        update = " ".join(update.split()).strip()

        if not base:
            return update

        if not update:
            return base

        base_lower = base.casefold()
        update_lower = update.casefold()

        if update_lower == base_lower:
            return base

        # Deepgram may return the full cumulative transcript.
        if update_lower.startswith(base_lower):
            return update

        # Avoid appending an older/smaller transcript twice.
        if base_lower.endswith(update_lower):
            return base

        # Handle partial overlap between the end of one segment and the
        # beginning of the next segment.
        max_overlap = min(len(base), len(update))
        for size in range(max_overlap, 0, -1):
            if base_lower[-size:] == update_lower[:size]:
                return (base + update[size:]).strip()

        return f"{base} {update}".strip()

    async def force_finalize(
        self,
    ) -> None:

        if (
            self._turn_finalized
            or (
                not self._final_transcript
                and self._last_interim is None
            )
        ):
            return

        if time.monotonic() - self._last_interim_time < 2.5:
            return

        # Cancel any scheduled delayed finalization to avoid racing
        if (
            self._utterance_end_task is not None
            and not self._utterance_end_task.done()
        ):
            self._utterance_end_task.cancel()
            self._utterance_end_task = None

        confidence = (
            self._last_interim.confidence
            if self._last_interim is not None
            else self._last_final_confidence
        )

        transcript = self._final_transcript

        if self._last_interim is not None:
            transcript = self._merge_transcripts(
                transcript,
                self._last_interim.text,
            )

        transcript = transcript.strip()

        if not transcript:
            return

        forced_event = TranscriptEvent(
            text=transcript,
            confidence=confidence,
            is_final=True,
            speech_final=True,
        )

        # Reset turn state completely for the next turn.
        self._turn_finalized = True
        self._last_interim = None
        self._final_transcript = ""
        self._last_final_confidence = 0.0
        self._last_interim_time = 0.0

        await self._events.put(forced_event)