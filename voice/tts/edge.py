import asyncio

import edge_tts

from config.logger import logger
from config.settings import settings


class EdgeTTS:

    def __init__(
        self,
    ):

        # Voice name configured in the application settings.
        
        # Example:
        #   en-US-AriaNeural
        
        # Edge TTS will use this voice to synthesize the text.
        self.voice = settings.EDGE_TTS_VOICE

    async def stream(
        self,
        text: str,
    ):

        # Ignore empty or whitespace-only text.
        if not text.strip():
            return

        logger.info(
            "Starting Edge-TTS stream: voice=%s text=%r",
            self.voice,
            text,
        )

        # Will hold the FFmpeg subprocess.
        #
        # We keep a reference so we can clean it up in finally.
        process = None

        try:

            # Start FFmpeg as a child process.
            #
            # FFmpeg receives audio through stdin and sends converted
            # PCM audio through stdout.
            #
            # Input:
            #   pipe:0 = stdin
            #
            # Output:
            #   pipe:1 = stdout
            #
            # Output audio format:
            #
            #   s16le       = signed 16-bit little-endian PCM
            #   pcm_s16le  = PCM signed 16-bit codec
            #   16000      = 16 kHz sample rate
            #   1          = mono
            #
            # The result therefore matches the PCM format expected by
            # the Speaker audio pipeline.
            process = await asyncio.create_subprocess_exec(

                "ffmpeg",

                # Only print actual errors.
                "-loglevel",
                "error",

                # Edge TTS yields MP3 audio frames. Explicitly tell
                # FFmpeg the input format so decoding starts immediately
                # when reading from a pipe.
                "-f",
                "mp3",
                "-i",
                "pipe:0",

                # Output raw PCM.
                "-f",
                "s16le",

                # Use signed 16-bit PCM.
                "-acodec",
                "pcm_s16le",

                # Convert to 16 kHz.
                "-ar",
                "16000",

                # Convert to mono.
                "-ac",
                "1",

                # Write converted audio to stdout.
                "pipe:1",

                # Give Python access to FFmpeg stdin.
                stdin=asyncio.subprocess.PIPE,

                # Give Python access to FFmpeg stdout.
                stdout=asyncio.subprocess.PIPE,

                # Capture FFmpeg errors.
                stderr=asyncio.subprocess.PIPE,
            )

            # Create the Edge TTS streaming request.
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
            )

            async def feed_ffmpeg():

                try:

                    # Edge TTS produces audio progressively.
                    
                    # We don't wait for the complete response.
                    # Each audio chunk is immediately passed to FFmpeg.
                    async for chunk in communicate.stream():

                        # Edge TTS can send different event types.
                        # We only care about actual audio data.
                        if chunk["type"] != "audio":
                            continue

                        # Get the actual audio bytes from the chunk.
                        data = chunk["data"]

                        # Ignore empty chunks.
                        if not data:
                            continue

                        # Feed the compressed Edge TTS audio into FFmpeg.
                        process.stdin.write(
                            data
                        )

                        # Wait until the pipe has accepted the data.
                        #
                        # This provides backpressure instead of allowing
                        # an unlimited amount of data to accumulate.
                        await process.stdin.drain()

                    # Edge TTS has finished producing audio.
                    #
                    # Closing stdin tells FFmpeg that no more input
                    # data is coming.
                    process.stdin.close()

                    try:

                        # Wait for the stdin pipe to finish closing.
                        await process.stdin.wait_closed()

                    except AttributeError:

                        # Some Python/runtime versions may not provide
                        # wait_closed() on this particular pipe object.
                        pass

                except asyncio.CancelledError:

                    # Allow cancellation to propagate.
                    #
                    # This is important if the user interrupts the
                    # assistant while TTS is speaking.
                    raise

            # Run the Edge TTS to FFmpeg input pipeline concurrently
            # with the FFmpeg output-reading loop below.
            feed_task = asyncio.create_task(
                feed_ffmpeg()
            )

            try:

                while True:

                    # Read approximately 100 ms of output audio.
                    #
                    # 16 kHz × 2 bytes/sample × 0.1 sec = 3200 bytes.
                    pcm = await process.stdout.read(
                        3200
                    )

                    # Empty output means FFmpeg has finished.
                    if not pcm:
                        break

                    # Yield the PCM chunk to the caller immediately.
                    #
                    # Because this function is an async generator,
                    # the caller can start sending the audio to the
                    # Speaker without waiting for the whole sentence.
                    yield pcm

            finally:

                # If the TTS feeding task is still running, cancel it.
                # This prevents a background task from continuing
                # after FFmpeg/output processing has stopped.
                if not feed_task.done():

                    feed_task.cancel()

                    try:

                        # Wait for cancellation to finish cleanly.
                        await feed_task

                    except asyncio.CancelledError:

                        # Cancellation here is expected.
                        pass

        except asyncio.CancelledError:

            # Log when the TTS stream is intentionally interrupted.
            logger.info(
                "Edge-TTS stream cancelled."
            )

            # Re-raise so cancellation reaches the caller.
            raise

        except Exception:

            # Log unexpected TTS/FFmpeg failures and re-raise them.
            logger.exception(
                "Edge-TTS stream failed."
            )

            raise

        finally:

            # Clean up the FFmpeg subprocess.
            #
            # This runs even if:
            #
            #   - TTS succeeds
            #   - TTS fails
            #   - the user interrupts playback
            #   - an exception occurs
            if process is not None:

                # returncode is None means FFmpeg is still running.
                if process.returncode is None:

                    # Stop the FFmpeg process.
                    process.kill()

                    try:

                        # Wait until the process has actually exited.
                        await process.wait()

                    except Exception:

                        # Don't allow cleanup errors to hide the
                        # original problem.
                        pass

        logger.info(
            "Edge-TTS stream finished."
        )