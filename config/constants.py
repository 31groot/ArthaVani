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


# Number of samples required by the Silero VAD for each inference frame.
# 512 samples at 16 kHz = 32 ms of audio.
VAD_FRAME_SAMPLES = 512

# Minimum amount of continuous speech required before
# considering the user to be speaking.
MIN_SPEECH_DURATION_MS = 250

# Minimum amount of continuous silence required before
# considering the user's speech to have ended.
MIN_SILENCE_DURATION_MS = 500

# Probability threshold used by the speech detector
# to classify an audio frame as speech.
SPEECH_THRESHOLD = 0.5

# Duration of one VAD frame in milliseconds.
# 512 samples at 16 kHz = 32 ms.
FRAME_DURATION_MS = 32


# Maximum amount of time allowed for an STT operation.
STT_TIMEOUT = 30

# Maximum amount of time allowed for an LLM operation.
LLM_TIMEOUT = 60

# Maximum amount of time allowed for a TTS operation.
TTS_TIMEOUT = 30


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


# Maximum number of messages retained by the conversation history.
MAX_MESSAGES = 20


# Number of taps/samples used by the acoustic echo cancellation filter.
FILTER_LENGTH = 512

# Estimated delay between the reference audio and microphone audio,
# expressed in samples.
DELAY_SAMPLES = 1600

# Adaptation step size for the echo cancellation filter.
MU = 0.4

#Full volume of the assistance
INITIAL_VOL = 1.0

#Volume dropped of assistance
DROPPED_VOL = 0.2

# Amount of speaker/reference audio retained for echo cancellation.
REFERENCE_BUFFER_SECONDS = 3.0


# Maximum number of conversation messages retained by the LLM worker.
MAX_CONVERSATION_HISTORY = 10


# Logging timestamp format.
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Application-wide log message format.
LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)-8s | "
    "%(name)s | "
    "%(message)s"
)