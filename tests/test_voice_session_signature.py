# tests/test_voice_session_signature.py
import inspect
from voice.web_pipeline import run_browser_voice_session

def test_run_browser_voice_session_accepts_agent_runner():
    params = inspect.signature(run_browser_voice_session).parameters
    assert "agent_runner" in params
