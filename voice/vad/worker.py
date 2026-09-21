import asyncio

from config.logger import logger

from voice.vad.buffer import AudioBuffer
from voice.vad.detector import SpeechDetector
from voice.vad.events import ConversationEvent
from voice.vad.silero import SileroVAD


class VADWorker:

    def __init__(
        self,
        vad: SileroVAD,
        detector: SpeechDetector,
        audio_queue: asyncio.Queue[bytes],
        conversation_queue: asyncio.Queue[ConversationEvent],
    ):

        # SileroVAD performs the actual neural-network inference.
        #
        # Input:
        #     fixed-size PCM audio frame
        #
        # Output:
        #     speech probability between approximately 0.0 and 1.0
        self.vad = vad

        # SpeechDetector takes the frame-by-frame probabilities from
        # Silero and turns them into high-level conversation events:
        #
        #     STARTED
        #     ENDED
        #
        # It also applies timing rules such as minimum speech and
        # silence durations.
        self.detector = detector

        # Queue containing processed microphone audio.
        
        self.audio_queue = audio_queue

        # Queue containing high-level conversation events produced
        # by SpeechDetector.
        #
        # Example:
        #
        #     SpeechState.STARTED
        #     SpeechState.ENDED
        self.conversation_queue = conversation_queue

        # AudioBuffer collects incoming microphone chunks until
        # enough bytes exist to create complete VAD frames.
        #
        # This is necessary because microphone callback chunks do not
        # necessarily match the exact frame size required by the VAD model.
        self.buffer = AudioBuffer()

        # Background asyncio task running the main VAD loop.
        self._task: asyncio.Task | None = None

    async def run(self):

        logger.info(
            "Starting VAD Worker..."
        )

        try:

            # Continuously process incoming microphone audio.
            while True:

                # Wait until the microphone provides another audio chunk.
                chunk = await self.audio_queue.get()

                # Add the chunk to the internal frame buffer.
                #
                # AudioBuffer may combine this chunk with leftover
                # audio from previous microphone callbacks.
                self.buffer.append(
                    chunk
                )

                # Extract every complete VAD-sized frame currently
                # available in the buffer.
                #
                # Any incomplete remainder stays inside AudioBuffer
                # for the next iteration.
                frames = self.buffer.pop_frames()

                # One call to pop_frames() can return multiple frames.
                #
                # Process each complete frame in chronological order.
                for frame in frames:

                    # Ask the Silero neural network how likely this
                    # particular frame is to contain human speech.
                    #
                    # Example:
                    #
                    #     0.03 → likely silence
                    #     0.91 → likely speech
                    probability = await self.vad.is_speech(
                        frame
                    )

                    # Convert the probability into application-level
                    # speech state logic.
                    #
                    # SpeechDetector may return:
                    #
                    #     None
                    #    
                    #     ENDED STARTED
                    #
                    # depending on the recent history of speech/silence
                    # frames.
                    event = self.detector.update(
                        probability
                    )

                    # Only send something downstream when an actual
                    # conversation state transition occurs.
                    #
                    # Most update() calls return None.
                    if event is not None:

                        await self.conversation_queue.put(
                            event
                        )

        except asyncio.CancelledError:

            # Cancellation is the normal way the worker is stopped.

            # Re-raise so asyncio knows this task was cancelled.
            raise

        except Exception:

            # Log unexpected failures with traceback.
            logger.exception(
                "VAD Worker crashed."
            )

            # Re-raise so the worker failure is visible to its caller.
            raise

    def start(
        self,
    ):

        # Prevent starting the same worker more than once.
        if self._task is not None:

            raise RuntimeError(
                "VAD Worker already started."
            )

        # Run the VAD loop as a background asyncio task.
        self._task = asyncio.create_task(
            self.run()
        )

    async def stop(
        self,
    ):

        # Nothing to stop if the worker has not been started.
        if self._task is None:
            return

        # Request cancellation of the background VAD task.
        self._task.cancel()

        try:

            # Wait for the worker to actually finish shutting down.
            await self._task

        except asyncio.CancelledError:

            # Cancellation is expected during shutdown.
            pass

        # Discard any incomplete audio frame still stored in the buffer.
        #
        # This prevents old audio from being combined with audio
        # from a future session.
        self.buffer.clear()

        # Remove the task reference so the worker can be started again.
        self._task = None

        logger.info(
            "VAD Worker stopped."
        )
