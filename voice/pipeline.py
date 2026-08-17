import asyncio

from config.constants import MAX_QUEUE_SIZE, FILTER_LENGTH, DELAY_SAMPLES
from config.logger import logger

from voice.audio.aec import EchoCanceller
from voice.audio.audio_fanout import AudioFanout
from voice.audio.microphone import Microphone
from voice.audio.speaker import Speaker

from voice.llm.azure import AzureLLM
from voice.llm.worker import LLMWorker

from voice.stt.deepgram import DeepgramClient
from voice.stt.worker import STTWorker

from voice.text.text_splitter import SentenceSplitter

from voice.tts.elevenlabs import ElevenLabsTTS
from voice.tts.worker import TTSWorker

from voice.vad.detector import SpeechDetector
from voice.vad.events import ConversationEvent, SpeechState
from voice.vad.silero import SileroVAD
from voice.vad.worker import VADWorker


class VoicePipeline:

    def __init__(self):

        # Queue receiving raw audio from the microphone.
        self.audio_input_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )

        # Separate queue for the VAD branch.
        self.vad_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )

        # Separate queue for the STT branch.
        self.stt_audio_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )

        # VAD sends speech STARTED/ENDED events here.
        self.conversation_queue: asyncio.Queue[
            ConversationEvent
        ] = asyncio.Queue()

        # STT sends transcript events here for the LLM worker.
        self.transcript_queue = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )

        # LLM sends complete sentences here for the TTS worker.
        self.sentence_queue = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )

        # TTS sends generated audio here for the speaker.
        self.speaker_audio_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )

        # Hardware / input-output components.
        self.echo_canceller = EchoCanceller(
            filter_length=FILTER_LENGTH,
            delay_samples=DELAY_SAMPLES,
        )

        self.microphone = Microphone(
            echo_canceller=self.echo_canceller,
        )

        self.speaker = Speaker(
            audio_queue=self.speaker_audio_queue,
            echo_canceller=self.echo_canceller,
        )

        # Takes microphone audio and sends the same audio
        # to both VAD and STT.
        self.audio_fanout = AudioFanout(
            input_queue=self.audio_input_queue,
            output_queues=[
                self.vad_queue,
                self.stt_audio_queue,
            ],
        )

        # VAD components.
        self.silero_vad = SileroVAD()
        self.speech_detector = SpeechDetector()

        self.vad_worker = VADWorker(
            vad=self.silero_vad,
            detector=self.speech_detector,
            audio_queue=self.vad_queue,
            conversation_queue=self.conversation_queue,
        )

        # Speech-to-text components.
        self.deepgram = DeepgramClient()

        self.stt_worker = STTWorker(
            deepgram=self.deepgram,
            audio_queue=self.stt_audio_queue,
            transcript_queue=self.transcript_queue,
        )

        # Text-to-speech components.
        self.elevenlabs = ElevenLabsTTS()

        self.tts_worker = TTSWorker(
            tts=self.elevenlabs,
            sentence_queue=self.sentence_queue,
            audio_queue=self.speaker_audio_queue,
        )

        # LLM components.
        self.azure_llm = AzureLLM()

        self.sentence_splitter = SentenceSplitter(
            sentence_queue=self.sentence_queue,
        )

        async def _on_new_turn() -> None:
            # A new turn interrupted a previous one: stop whatever
            # TTS is speaking/queued and clear the speaker's
            # playback buffer so stale audio doesn't keep playing.
            await self.tts_worker.interrupt()
            await self.speaker.clear()

        self._on_new_turn = _on_new_turn

        self.llm_worker = LLMWorker(
            llm=self.azure_llm,
            splitter=self.sentence_splitter,
            transcript_queue=self.transcript_queue,
            on_new_turn=_on_new_turn,
        )

        # Stores the main pipeline task.
        self._run_task: asyncio.Task | None = None

        # Stores the barge-in listener task.
        self._barge_in_task: asyncio.Task | None = None

    async def start(self) -> None:

        # Prevent starting the same pipeline twice.
        if self._run_task is not None:
            raise RuntimeError(
                "Voice Pipeline already started."
            )

        logger.info("Starting Voice Pipeline...")

        # Start hardware.
        await self.microphone.start()
        await self.speaker.start()

        # Start the audio distribution system.
        self.audio_fanout.start()

        # Start all processing workers.
        self.vad_worker.start()
        self.stt_worker.start()
        self.llm_worker.start()
        self.tts_worker.start()

        # Start the main loop that moves microphone audio
        # into the pipeline.
        self._run_task = asyncio.create_task(
            self.run()
        )

        # Start the loop that listens for VAD speech-start events
        # and uses them to interrupt any in-progress response
        # (true barge-in — doesn't wait for STT to finish).
        self._barge_in_task = asyncio.create_task(
            self._barge_in_loop()
        )

        logger.info("Voice Pipeline started.")

    async def _barge_in_loop(self) -> None:

        logger.info("Barge-in listener started.")

        try:

            while True:

                event = await self.conversation_queue.get()

                logger.info(
                    f"Conversation event: {event.state}"
                )

                if event.state is SpeechState.POSSIBLE_STARTED:
                    # Eager, low-confidence signal — duck the
                    # assistant's volume immediately rather than
                    # waiting out the full confirmation delay.
                    # Shrinks the acoustic overlap window that was
                    # causing the user's opening words to get lost
                    # during real barge-ins.
                    self.speaker.duck()
                    continue

                if event.state is SpeechState.POSSIBLE_ENDED:
                    # The eager signal didn't pan out (e.g. a brief
                    # noise) — restore full volume.
                    self.speaker.unduck()
                    continue

                if event.state is SpeechState.ENDED:
                    # Safety net: if Deepgram's own EndOfTurn
                    # doesn't arrive shortly after our VAD says the
                    # user has gone quiet, promote whatever interim
                    # transcript it last gave us instead of letting
                    # the turn hang or silently merge into the next
                    # utterance.
                    asyncio.create_task(
                        self._finalize_watchdog()
                    )
                    continue

                if event.state is not SpeechState.STARTED:
                    continue

                logger.info(
                    "Speech detected, interrupting any "
                    "in-progress response."
                )

                await self.llm_worker.interrupt()
                await self._on_new_turn()

        except asyncio.CancelledError:

            logger.info("Barge-in listener stopped.")

            raise

        except Exception:

            logger.exception("Barge-in listener crashed.")

            raise

    async def _finalize_watchdog(self) -> None:

        # Give Deepgram a window to send its own EndOfTurn before
        # we step in. Long enough to not race a normal EndOfTurn,
        # short enough not to noticeably add to response latency.
        await asyncio.sleep(1.2)

        await self.deepgram.force_finalize()

    async def run(self) -> None:

        logger.info(
            "Voice Pipeline audio loop started."
        )

        try:

            while True:

                # Wait for the next audio chunk from the microphone.
                audio = await self.microphone.read()

                # Put the audio into the main queue.
                # AudioFanout will later distribute it to VAD and STT.
                await self.audio_input_queue.put(
                    audio
                )

        except asyncio.CancelledError:

            logger.info(
                "Voice Pipeline audio loop stopped."
            )

            # Allow cancellation to propagate correctly.
            raise

        except Exception:

            # Log unexpected errors before propagating them.
            logger.exception(
                "Voice Pipeline audio loop crashed."
            )

            raise

    async def stop(self) -> None:

        logger.info("Stopping Voice Pipeline...")

        # Stop the main pipeline loop.
        if self._run_task is not None:

            self._run_task.cancel()

            # Wait until the task has actually finished.
            try:

                await self._run_task

            except asyncio.CancelledError:

                pass

            self._run_task = None

        # Stop the barge-in listener.
        if self._barge_in_task is not None:

            self._barge_in_task.cancel()

            try:
                await self._barge_in_task
            except asyncio.CancelledError:
                pass

            self._barge_in_task = None

        # Stop components in the pipeline.
        await self.microphone.stop()
        await self.audio_fanout.stop()

        await self.vad_worker.stop()
        await self.stt_worker.stop()
        await self.llm_worker.stop()
        await self.tts_worker.stop()

        # Stop audio playback last.
        await self.speaker.stop()

        logger.info("Voice Pipeline stopped.")