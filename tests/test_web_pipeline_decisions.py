"""Decision-logic tests for duck / barge-in using a stubbed pipeline."""
import asyncio, sys, time, types
from types import SimpleNamespace

for name in ["finance_agent.conversation", "voice.llm.worker", "voice.stt.deepgram",
             "voice.stt.worker", "voice.text.text_splitter", "voice.tts.edge",
             "voice.tts.worker", "voice.vad.silero", "voice.vad.worker",
             "finance_agent.runner", "finance_agent"]:
    if name not in sys.modules:
        m = types.ModuleType(name)
        for attr in ["ConversationIdentity", "LLMWorker", "DeepgramClient", "STTWorker",
                     "SentenceSplitter", "EdgeTTS", "TTSWorker", "SileroVAD", "VADWorker",
                     "FinanceAgentRunner"]:
            setattr(m, attr, object)
        sys.modules[name] = m

from voice.web_pipeline import BrowserVoicePipeline  # noqa: E402
from voice.audio.echo_guard import EchoGuard  # noqa: E402
from voice.vad.detector import SpeechDetector  # noqa: E402
from voice.vad.events import ConversationEvent, SpeechState  # noqa: E402
from collections import deque  # noqa: E402

SPOKEN = "Your portfolio is worth twenty thousand rupees and your largest holding is Reliance."


def make():
    p = object.__new__(BrowserVoicePipeline)
    p.echo_guard = EchoGuard(); p.echo_guard.note_spoken(SPOKEN)
    p.speech_detector = SpeechDetector()
    p.conversation_queue = asyncio.Queue()
    p.events, p.confirmed = [], []
    p._tts_active = True; p._tts_barge_in_armed = True; p._barge_in_in_progress = False
    p._tts_interrupt_ready_at = 0.0; p._user_speech_active = False
    p._possible_speech_active = False; p._ducked = False; p._soft_duck_stamp = 0.0
    p._verify_task = None; p._recent_interims = deque(maxlen=16)
    p._echo_tail_until = 0.0; p._interim_candidates = 0; p._interim_candidate_time = 0.0
    p._response_active = True

    async def q(ev): p.events.append(ev["type"])
    async def confirm(reason):
        p.confirmed.append(reason); p._barge_in_in_progress = True
    p._queue_event, p._confirm_barge_in = q, confirm
    return p


def interim(text):
    return SimpleNamespace(text=text, is_final=False, confidence=0.9)


async def drive(p, states, wait=0.0):
    task = asyncio.create_task(p._barge_in_loop())
    for s in states:
        await p.conversation_queue.put(ConversationEvent(state=s))
    await asyncio.sleep(0.05)
    if wait: await asyncio.sleep(wait)
    task.cancel()


def test_possible_started_does_not_duck_on_vad_alone():
    p = make()
    asyncio.run(drive(p, [SpeechState.POSSIBLE_STARTED]))
    assert "duck" not in p.events


def test_possible_started_ducks_when_stt_shows_user_text():
    p = make()
    p._recent_interims.append((time.monotonic(), "wait show me infosys", False, 3))
    asyncio.run(drive(p, [SpeechState.POSSIBLE_STARTED]))
    assert "duck" in p.events


def test_started_rejected_when_stt_hears_echo():
    async def go():
        p = make()
        p._recent_interims.append((time.monotonic(), "your portfolio is worth", True, 0))
        await drive(p, [SpeechState.STARTED], wait=0.4)
        return p
    p = asyncio.run(go())
    assert p.confirmed == []


def test_started_confirms_fast_when_stt_shows_user_text():
    async def go():
        p = make()
        p._recent_interims.append((time.monotonic(), "stop show me tcs", False, 3))
        await drive(p, [SpeechState.STARTED], wait=0.1)
        return p
    assert asyncio.run(go()).confirmed


def test_started_without_any_evidence_confirms_after_short_window():
    async def go():
        p = make()
        await drive(p, [SpeechState.STARTED], wait=0.1)
        early = list(p.confirmed)
        await asyncio.sleep(0.3)
        return early, p.confirmed
    early, late = asyncio.run(go())
    assert early == [] and late


def test_vad_flags_no_longer_bypass_interim_confirmation():
    async def go():
        p = make()
        p._possible_speech_active = True          # VAD candidate (maybe echo)
        p._user_speech_active = True
        await p._on_transcript(interim("wait"))   # one weak non-echo interim
        return p
    p = asyncio.run(go())
    assert p.confirmed == []


def test_second_interim_or_strong_interim_interrupts():
    async def go():
        p = make()
        await p._on_transcript(interim("wait"))
        await p._on_transcript(interim("wait show"))
        q = make()
        await q._on_transcript(interim("show infosys news"))
        return p, q
    p, q = asyncio.run(go())
    assert p.confirmed and q.confirmed


def test_echo_interim_never_interrupts():
    async def go():
        p = make()
        for t in ["your portfolio", "your portfolio is worth twenty thousand"]:
            await p._on_transcript(interim(t))
        return p
    p = asyncio.run(go())
    assert p.confirmed == [] and "interim_text" not in p.events
