# Microphone sample rate (Hz)
SAMPLE_RATE = 16_000

# Mono audio
CHANNELS = 1

# Audio chunk size (frames)
CHUNK_SIZE = 1024

# 16-bit PCM audio
SAMPLE_WIDTH = 2



# Minimum speech duration (milliseconds)
MIN_SPEECH_DURATION_MS = 250

# Minimum silence duration before considering speech ended (milliseconds)
MIN_SILENCE_DURATION_MS = 500


STT_TIMEOUT = 30

LLM_TIMEOUT = 60

TTS_TIMEOUT = 30




MAX_QUEUE_SIZE = 100



MAX_CONVERSATION_HISTORY = 10




LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)-8s | "
    "%(name)s | "
    "%(message)s"
)