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
        self._last_interim: TranscriptEvent | None = None

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

        # Deepgram sends a separate UtteranceEnd event when it
        # believes the user has finished a speaking turn.
        #
        # We use this as our main "finalize this turn" signal.
        if isinstance(
            message,
            ListenV1UtteranceEnd,
        ):

            self._on_utterance_end()

            return

        # Ignore Deepgram messages that are not transcript results.
        if not isinstance(
            message,
            ListenV1Results,
        ):
            return

        # Get the possible transcription alternatives.
        alternatives = message.channel.alternatives

        # Use the highest-ranked alternative.
        transcript = alternatives[0].transcript if alternatives else ""

        # Get the confidence score of the highest-ranked alternative.
        confidence =  alternatives[0].confidence if alternatives else 0.0


        # Ignore messages that contain no actual transcript text.
        if not transcript:
            return

        # Convert Deepgram's transcript into our own application-level
        # TranscriptEvent object.
        #
       
        # We intentionally mark this as is_final=False even if
        # Deepgram's own message.is_final flag says something else.
        #
        # Our application uses UtteranceEnd as the real signal
        # that the user's turn is finished.
        #don't make the rest of the application depend directly on
        # Deepgram's event format
       
        event = TranscriptEvent(
            text=transcript,
            confidence=confidence,
            is_final=False,
        )

        # Log both our transcript and Deepgram's own flags for debugging.
        logger.info(
            "STT interim: text=%r confidence=%.3f is_final=%s "
            "speech_final=%s",
            transcript,
            confidence,
            message.is_final,
            message.speech_final,
        )

        # Remember this as the latest transcript candidate.
        self._last_interim = event

        # We now have an active/unfinalized speech turn.
        self._turn_finalized = False

        # Remember when this transcript arrived.
        #
        # force_finalize() uses this to decide whether the user
        # has been silent long enough to force a final result.
        self._last_interim_time = (
            time.monotonic()
        )

        # Deepgram's callback may not be executing directly inside
        # our asyncio event-loop context.
        #
        # call_soon_threadsafe() safely schedules the queue insertion
        # on the asyncio event loop.
        if (
            self.loop is not None
            and self.loop.is_running()
        ):

            self.loop.call_soon_threadsafe(
                self._events.put_nowait,
                event,
            )

    def _on_utterance_end(
        self,
    ) -> None:

        # Ignore duplicate utterance-end events or cases where
        # we don't currently have a transcript candidate.
        if (
            self._turn_finalized
            or self._last_interim is None
        ):
            return

        # Use the latest transcript candidate as the final
        # user utterance.
        transcript = (
            self._last_interim.text
        )

        confidence = (
            self._last_interim.confidence
        )

        logger.info(
            "STT final: text=%r confidence=%.3f "
            "(via UtteranceEnd)",
            transcript,
            confidence,
        )

        # Convert the latest interim transcript into a final
        # application-level TranscriptEvent.
        final_event = TranscriptEvent(
            text=transcript,
            confidence=confidence,
            is_final=True,
        )

        # Mark the current turn as completed.
        self._turn_finalized = True

        # Remove the old transcript candidate.
        self._last_interim = None

        # Reset the timestamp because there is no active
        # interim transcript anymore.
        self._last_interim_time = 0.0

        # Safely add the final event to the asyncio queue.
        if (
            self.loop is not None
            and self.loop.is_running()
        ):

            self.loop.call_soon_threadsafe(
                self._events.put_nowait,
                final_event,
            )

    async def force_finalize(
        self,
    ) -> None:

        # Nothing to finalize if:
        #
        #   - the turn is already finalized, or
        #   - there is no current transcript candidate.
        if (
            self._turn_finalized
            or self._last_interim is None
        ):
            return

        # If the latest transcript arrived less than 2.5 seconds ago,
        # don't force-finalize yet.
        #
        # This gives Deepgram's normal UtteranceEnd mechanism
        # a chance to fire.
        if (
            time.monotonic()
            - self._last_interim_time
            < 2.5
        ):
            return

        # Deepgram did not send UtteranceEnd within the expected time,
        # so use our latest interim transcript as a final result.
        forced_event = TranscriptEvent(
            text=self._last_interim.text,
            confidence=self._last_interim.confidence,
            is_final=True,
        )

        # Mark the turn as finalized.
        self._turn_finalized = True

        # Clear the old transcript candidate.
        self._last_interim = None

        # Reset the timestamp for consistency.
        self._last_interim_time = 0.0

        # force_finalize() already runs inside our asyncio event loop,
        # so we can directly await the queue operation.
        await self._events.put(
            forced_event
        )