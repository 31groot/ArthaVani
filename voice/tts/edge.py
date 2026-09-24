import asyncio
import io

import av
import edge_tts

from config.logger import logger
from config.settings import settings


class EdgeTTS:
    """Edge-TTS adapter that always yields 16 kHz mono s16 PCM.

    The web and desktop voice pipelines both consume raw PCM bytes from the
    TTS queue. Edge-TTS returns compressed MP3 audio, so we decode it in-process
    with PyAV instead of spawning FFmpeg for every sentence.
    """

    def __init__(self) -> None:
        self.voice = settings.EDGE_TTS_VOICE

    async def stream(self, text: str):
        if not text.strip():
            return

        logger.info(
            "Starting Edge-TTS stream: voice=%s text=%r",
            self.voice,
            text,
        )

        compressed = bytearray()

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
            )

            # Edge-TTS emits compressed audio chunks. Collect the sentence so
            # it can be decoded deterministically into the PCM format expected
            # by the existing audio queues.
            async for chunk in communicate.stream():
                if chunk.get("type") != "audio":
                    continue
                data = chunk.get("data") or b""
                if data:
                    compressed.extend(data)

            if not compressed:
                raise RuntimeError(
                    "Edge-TTS returned no audio data for the requested sentence."
                )

            logger.debug(
                "Edge-TTS produced %d compressed audio bytes.",
                len(compressed),
            )

            pcm = bytearray()

            # Decode the MP3 in-process. This avoids the intermittent FFmpeg
            # subprocess crashes seen in the web TTS path (exit -11 / SIGSEGV)
            # and avoids stdin/stdout transport races entirely.
            with av.open(io.BytesIO(compressed), format="mp3", mode="r") as container:
                audio_stream = next(
                    (stream for stream in container.streams if stream.type == "audio"),
                    None,
                )
                if audio_stream is None:
                    raise RuntimeError("Edge-TTS audio contains no audio stream.")

                resampler = av.audio.resampler.AudioResampler(
                    format="s16",
                    layout="mono",
                    rate=16000,
                )

                for frame in container.decode(audio=audio_stream.index):
                    for out_frame in resampler.resample(frame):
                        pcm.extend(out_frame.to_ndarray().reshape(-1).astype("<i2", copy=False).tobytes())

                # Flush any buffered resampler samples.
                for out_frame in resampler.resample(None):
                    pcm.extend(out_frame.to_ndarray().reshape(-1).astype("<i2", copy=False).tobytes())

            if not pcm:
                raise RuntimeError("PyAV decoded no PCM audio from Edge-TTS output.")

            logger.info(
                "Edge-TTS decoded %d compressed bytes to %d PCM bytes.",
                len(compressed),
                len(pcm),
            )

            # Existing TTS queues expect 16 kHz, mono, signed 16-bit PCM.
            # 16,000 samples/s * 2 bytes/sample * 100 ms = 3,200 bytes.
            for offset in range(0, len(pcm), 3200):
                chunk = bytes(pcm[offset : offset + 3200])
                if chunk:
                    yield chunk

        except asyncio.CancelledError:
            logger.info("Edge-TTS stream cancelled.")
            raise
        except Exception:
            logger.exception("Edge-TTS stream failed.")
            raise
        finally:
            logger.info("Edge-TTS stream finished.")
