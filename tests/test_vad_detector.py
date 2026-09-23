from voice.vad.detector import SpeechDetector
from voice.vad.events import SpeechState


def test_possible_started_happens_before_confirmed_started():
    detector = SpeechDetector(
        threshold=0.5,
        frame_duration_ms=32,
    )

    # 32 ms: not enough for possible speech.
    assert detector.update(0.9) is None

    # 64 ms: early barge-in duck signal.
    event = detector.update(0.9)

    assert event is not None
    assert event.state == SpeechState.POSSIBLE_STARTED

    # 96 ms: still below confirmed barge-in threshold.
    assert detector.update(0.9) is None

    # 128 ms: confirmed barge-in.
    event = detector.update(0.9)

    assert event is not None
    assert event.state == SpeechState.STARTED


def test_possible_speech_can_be_cancelled():
    detector = SpeechDetector(
        threshold=0.5,
        frame_duration_ms=32,
    )

    assert detector.update(0.9) is None

    event = detector.update(0.9)

    assert event is not None
    assert event.state == SpeechState.POSSIBLE_STARTED

    # 32 ms silence.
    assert detector.update(0.0) is None

    # 64 ms silence cancels the early candidate.
    event = detector.update(0.0)

    assert event is not None
    assert event.state == SpeechState.POSSIBLE_ENDED


def test_confirmed_speech_uses_normal_silence_duration():
    detector = SpeechDetector(
        threshold=0.5,
        frame_duration_ms=32,
    )

    # 4 frames = 128 ms -> confirmed STARTED.
    for _ in range(4):
        event = detector.update(0.9)

    assert event is not None
    assert event.state == SpeechState.STARTED

    # 15 frames = 480 ms: not enough to end the turn.
    for _ in range(15):
        assert detector.update(0.0) is None

    # 16 frames = 512 ms: confirmed ENDED.
    event = detector.update(0.0)

    assert event is not None
    assert event.state == SpeechState.ENDED
