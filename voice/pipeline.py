import asyncio

from config.constants import MAX_QUEUE_SIZE
from config.logger import logger

from voice.audio.audio_fanout import AudioFanout
from voice.audio.microphone import Microphone
from voice.audio.speaker import Speaker

from voice.llm.azure import AzureLLM
from voice.llm.worker import LLMWorker

from voice.stt.deepgram import DeepgramClient
from voice.stt.worker import STTWorker

from voice.text.splitter import SentenceSplitter

from voice.tts.elevenlabs import ElevenLabsTTS
from voice.tts.worker import TTSWorker

from voice.vad.detector import SpeechDetector
from voice.vad.events import ConversationEvent
from voice.vad.silero import SileroVAD
from voice.vad.worker import VADWorker


class VoicePipeline:

    def __init__(self):

        self.audio_input_queue: asyncio.Queue[bytes] = (
            asyncio.Queue(
                maxsize=MAX_QUEUE_SIZE
            )
        )

        self.vad_queue: asyncio.Queue[bytes] = (
            asyncio.Queue(
                maxsize=MAX_QUEUE_SIZE
            )
        )

        self.stt_audio_queue: asyncio.Queue[bytes] = (
            asyncio.Queue(
                maxsize=MAX_QUEUE_SIZE
            )
        )

        self.conversation_queue: asyncio.Queue[
            ConversationEvent
        ] = asyncio.Queue()


        self.transcript_queue = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )


        self.sentence_queue = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )


        self.speaker_audio_queue: asyncio.Queue[bytes] = (
            asyncio.Queue(
                maxsize=MAX_QUEUE_SIZE
            )
        )

        self.microphone = Microphone()

        self.speaker = Speaker(
            audio_queue=self.speaker_audio_queue,
        )


        self.audio_fanout = AudioFanout(
            input_queue=self.audio_input_queue,
            output_queues=[
                self.vad_queue,
                self.stt_audio_queue,
            ],
        )


        self.silero_vad = SileroVAD()

        self.speech_detector = SpeechDetector()

        self.vad_worker = VADWorker(
            vad=self.silero_vad,
            detector=self.speech_detector,
            audio_queue=self.vad_queue,
            conversation_queue=self.conversation_queue,
        )

        self.deepgram = DeepgramClient()

        self.stt_worker = STTWorker(
            deepgram=self.deepgram,
            audio_queue=self.stt_audio_queue,
            transcript_queue=self.transcript_queue,
        )


        self.azure_llm = AzureLLM()

        self.sentence_splitter = SentenceSplitter(
            sentence_queue=self.sentence_queue,
        )

        self.llm_worker = LLMWorker(
            llm=self.azure_llm,
            splitter=self.sentence_splitter,
            transcript_queue=self.transcript_queue,
        )


        self.elevenlabs = ElevenLabsTTS()

        self.tts_worker = TTSWorker(
            tts=self.elevenlabs,
            sentence_queue=self.sentence_queue,
            audio_queue=self.speaker_audio_queue,
        )


        self._run_task: asyncio.Task | None = None

    async def start(self) -> None:

        if self._run_task is not None:
            raise RuntimeError(
                "Voice Pipeline already started."
            )

        logger.info("Starting Voice Pipeline...")


        await self.microphone.start()
        await self.speaker.start()


        self.audio_fanout.start()


        self.vad_worker.start()
        self.stt_worker.start()
        self.llm_worker.start()
        self.tts_worker.start()

        self._run_task = asyncio.create_task(
            self.run()
        )

        logger.info("Voice Pipeline started.")

    async def run(self) -> None:


        logger.info(
            "Voice Pipeline audio loop started."
        )

        try:

            while True:

                audio = await self.microphone.read()

                await self.audio_input_queue.put(
                    audio
                )

        except asyncio.CancelledError:

            logger.info(
                "Voice Pipeline audio loop stopped."
            )

            raise

        except Exception:

            logger.exception(
                "Voice Pipeline audio loop crashed."
            )

            raise

    async def stop(self) -> None:
        """
        Stop the complete voice pipeline.
        """

        logger.info("Stopping Voice Pipeline...")

        if self._run_task is not None:

            self._run_task.cancel()

            try:

                await self._run_task

            except asyncio.CancelledError:

                pass

            self._run_task = None


        await self.microphone.stop()


        await self.audio_fanout.stop()


        await self.vad_worker.stop()
        await self.stt_worker.stop()
        await self.llm_worker.stop()
        await self.tts_worker.stop()


        await self.speaker.stop()

        logger.info("Voice Pipeline stopped.")