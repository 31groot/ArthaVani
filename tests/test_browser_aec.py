import sys, types
import numpy as np

calls = []
class FakeAPM:
    def __init__(self, **kw): pass
    def set_stream_format(self, *a): pass
    def set_reverse_stream_format(self, *a): pass
    def set_system_delay(self, ms): calls.append(("delay", ms))
    def process_reverse_stream(self, b): calls.append(("ref", len(b)))
    def process_stream(self, b): calls.append(("near", len(b))); return b
    def has_echo(self): return False
sys.modules["webrtc_audio_processing"] = types.SimpleNamespace(AudioProcessingModule=FakeAPM)

from voice.audio.browser_aec import BrowserEchoProcessor  # noqa: E402
from voice.audio.webrtc_aec import EchoCanceller  # noqa: E402


def pcm(v, n=320):
    return np.full(n, v, dtype="<i2").tobytes()


def test_silent_reference_bypasses_aec():
    calls.clear()
    p = BrowserEchoProcessor(EchoCanceller())
    assert p.process(pcm(100), pcm(0)) == pcm(100)
    assert not [c for c in calls if c[0] in ("ref", "near")]


def test_active_reference_runs_lockstep_and_keeps_length():
    calls.clear()
    p = BrowserEchoProcessor(EchoCanceller())
    out = p.process(pcm(100), pcm(500))
    assert len(out) == 640
    kinds = [c[0] for c in calls if c[0] in ("ref", "near")]
    assert kinds == ["ref", "ref", "near", "near"]


def test_tail_keeps_aec_running_after_reference_stops():
    calls.clear()
    p = BrowserEchoProcessor(EchoCanceller(), tail_ms=100)
    p.process(pcm(100), pcm(500))
    calls.clear()
    p.process(pcm(100), pcm(0))          # still inside 100 ms tail
    assert any(c[0] == "near" for c in calls)
    for _ in range(10): p.process(pcm(100), pcm(0))
    calls.clear()
    p.process(pcm(100), pcm(0))
    assert not calls


def test_odd_length_is_padded_and_trimmed():
    p = BrowserEchoProcessor(EchoCanceller())
    assert len(p.process(pcm(1, 300), pcm(500, 300))) == 600


def test_delay_is_clamped():
    calls.clear()
    p = BrowserEchoProcessor(EchoCanceller())
    assert p.set_delay_ms(9999) == 500
    assert p.set_delay_ms(None) == 100
