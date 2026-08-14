# Microphone sample rate (Hz)
SAMPLE_RATE = 16_000

# Mono audio
CHANNELS = 1

# Audio chunk size (frames)
CHUNK_SIZE = 1024

# 16-bit PCM audio
SAMPLE_WIDTH = 2

# Silero VAD frame size (samples)
# 512 samples at 16 kHz = 32 ms
VAD_FRAME_SAMPLES = 512

# Minimum speech duration (milliseconds)
MIN_SPEECH_DURATION_MS = 250

# Minimum silence duration before considering speech ended (milliseconds)
MIN_SILENCE_DURATION_MS = 500

# Threshold for speech detection
SPEECH_THRESHOLD = 0.5

FRAME_DURATION_MS = 32

STT_TIMEOUT = 30

LLM_TIMEOUT = 60

TTS_TIMEOUT = 30



MAX_QUEUE_SIZE = 100

#maximum messages for history queue
MAX_MESSAGES =  20




MAX_CONVERSATION_HISTORY = 10




LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)-8s | "
    "%(name)s | "
    "%(message)s"
)