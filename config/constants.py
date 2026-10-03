# Application audio sample rate (Hz).
# All audio after the microphone resampling stage uses this rate.
SAMPLE_RATE = 16_000

# Number of audio channels.
# ArthaVani currently uses mono audio.
CHANNELS = 1

# Number of audio samples captured per microphone callback.
CHUNK_SIZE = 1024

# Number of bytes used by each PCM audio sample.
# int16 = 2 bytes per sample.
SAMPLE_WIDTH = 2

# MIC_INPUT_GAIN controls microphone volume.
# 1.0 → unchanged
# 2.0 → roughly twice the amplitude
# 0.5 → half the amplitude
MIC_INPUT_GAIN = 0.5

# Number of samples required by the Silero VAD for each inference frame.
# 512 samples at 16 kHz = 32 ms of audio.
VAD_FRAME_SAMPLES = 512

# Early speech detection used for fast barge-in ducking.
#
# The speaker is ducked quickly after a small amount of
# continuous speech
POSSIBLE_SPEECH_DURATION_MS = 64
POSSIBLE_SILENCE_DURATION_MS = 64

# Confirmed barge-in threshold.
#
# The speaker is ducked at POSSIBLE_SPEECH_DURATION_MS,
# then the active response is interrupted once speech
# continues for this duration.
BARGE_IN_CONFIRMATION_DURATION_MS = 128

# Minimum amount of continuous silence required before
# considering the user's speech to have ended.
MIN_SILENCE_DURATION_MS = 500

# Probability threshold used by the speech detector
# to classify an audio frame as speech.
SPEECH_THRESHOLD = 0.5

# Duration of one VAD frame in milliseconds.
# 512 samples at 16 kHz = 32 ms.
FRAME_DURATION_MS = 32

# Native sample rate of the physical microphone hardware.
# The microphone captures audio at 44.1 kHz.
MIC_SAMPLE_RATE = 44_100

# Sample rate used by the rest of the application.
# Microphone audio is resampled from MIC_SAMPLE_RATE to this rate
# before entering the main audio pipeline.
APPLICATION_SAMPLE_RATE = 16_000


# Maximum number of items allowed in bounded audio/event queues.
# Prevents unlimited memory growth when a consumer falls behind.
MAX_QUEUE_SIZE = 300

#Full volume of the assistance
INITIAL_VOL = 1.0

#Volume dropped of assistance
DROPPED_VOL = 0.2

# WebRTC's AEC operates on fixed 10ms frames.
FRAME_MS = 10
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 160 samples @16kHz

# Configuration value understood by the WebRTC audio-processing library.
# It means desktop AEC mode
AEC_TYPE_DESKTOP = 2

# estimate (ms) of the speaker->mic round trip, used
# only to seed WebRTC's internal delay search .
INITIAL_SYSTEM_DELAY_MS = 100

# Retry policy for rate-limit-shaped LLM provider failures only (e.g. Groq's
# tokens-per-minute cap). Other failures (auth, network, bad model name)
# fail immediately -- retrying those just delays a response that will
# never succeed.
RATE_LIMIT_MAX_ATTEMPTS = 3
RATE_LIMIT_BASE_DELAY_SECONDS = 1.5


# Keep the provider request comfortably below small/free-tier TPM caps.
# The exact token count varies by tokenizer, so we reduce the two biggest
# sources of prompt growth: unneeded tool schemas and old tool-call history.
MAX_HISTORY_TURNS = 3


# Logging timestamp format.
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Application-wide log message format.
LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)-8s | "
    "%(name)s | "
    "%(message)s"
)
