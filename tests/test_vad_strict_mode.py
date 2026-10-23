from voice.vad.detector import SpeechDetector
from voice.vad.events import SpeechState


def run(det, p, n):
    return [e.state for e in (det.update(p) for _ in range(n)) if e]


def test_strict_mode_ignores_weak_speech_probability():
    d = SpeechDetector(); d.set_strict(True)
    assert run(d, 0.6, 20) == []


def test_strict_mode_needs_longer_speech():
    d = SpeechDetector(); d.set_strict(True)
    assert run(d, 0.9, 3) == []
    assert run(d, 0.9, 1) == [SpeechState.POSSIBLE_STARTED]      # 128 ms
    assert run(d, 0.9, 5) == []
    assert run(d, 0.9, 1) == [SpeechState.STARTED]               # 320 ms


def test_normal_mode_unchanged():
    d = SpeechDetector()
    assert run(d, 0.6, 2) == [SpeechState.POSSIBLE_STARTED]
