"""Voice-chat session thread: pause/stream/resume orchestration with fakes."""

import threading
import time
from unittest.mock import patch

from voice_chat.client import VoiceChatError
from voice_chat.session import VoiceChatSession


class FakeListener:
    def __init__(self, log=None):
        self.calls = log if log is not None else []

    def pause(self):
        self.calls.append("pause")

    def resume(self):
        self.calls.append("resume")


class FakeResp:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def read(self, n):
        return self.chunks.pop(0) if self.chunks else b""


class FakeClient:
    def __init__(self, chunks=(b"aa", b"bb"), conv_id="c1", error=None, gate=None):
        self.chunks = chunks
        self.conv_id = conv_id
        self.error = error
        self.gate = gate
        self.chat_calls = []
        self.closed = False

    def chat(self, text, conversation_id=None):
        self.chat_calls.append((text, conversation_id))
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.error is not None:
            raise self.error
        return FakeResp(self.chunks), 24000, 1, self.conv_id

    def close(self):
        self.closed = True


def make_session(listener=None, client=None, config=None, events=None):
    cfg = {"voice_chat": {"enabled": True, **(config or {})}}
    events = events if events is not None else []
    session = VoiceChatSession(cfg, listener or FakeListener(), events.append)
    if client is not None:
        session.client = client       # bypasses _ensure_client's credential check
    return session, events


def wait_idle(session, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with session._lock:
            if not session._active:
                return
        time.sleep(0.01)
    raise AssertionError("session did not finish")


@patch("voice_chat.session.AudioOutput")
def test_success_flow(mock_output_cls):
    listener = FakeListener()
    client = FakeClient(chunks=(b"aa", b"bb"))
    session, events = make_session(listener, client)
    session.handle("hello")
    wait_idle(session)

    assert [e["state"] for e in events] == ["start", "end"]
    assert listener.calls == ["pause", "resume"]
    output = mock_output_cls.return_value
    assert [c.args[0] for c in output.write.call_args_list] == [b"aa", b"bb"]
    output.close.assert_called_once()
    output.abort.assert_not_called()
    mock_output_cls.assert_called_once_with(24000, 1, command=None)
    assert client.closed is True


def test_resume_happens_before_end_event():
    log = []
    listener = FakeListener(log)                 # pause/resume land in the shared log
    session = VoiceChatSession({"voice_chat": {"enabled": True}}, listener,
                               lambda e: log.append(e["state"]))
    session.client = FakeClient()
    with patch("voice_chat.session.AudioOutput"):
        session.handle("hi")
        wait_idle(session)
    assert log == ["start", "pause", "resume", "end"]


@patch("voice_chat.session.AudioOutput")
def test_conversation_id_reused_across_turns(mock_output_cls):
    client = FakeClient(conv_id="c9")
    session, _ = make_session(client=client)
    session.handle("first")
    wait_idle(session)
    session.handle("second")
    wait_idle(session)
    assert client.chat_calls == [("first", None), ("second", "c9")]


@patch("voice_chat.session.AudioOutput")
def test_client_error_emits_error_and_resumes(mock_output_cls):
    listener = FakeListener()
    client = FakeClient(error=VoiceChatError("AIUI down"))
    session, events = make_session(listener, client)
    session.handle("hello")
    wait_idle(session)

    assert [e["state"] for e in events] == ["start", "error"]
    assert "AIUI down" in events[-1]["error"]
    assert listener.calls == ["pause", "resume"]
    mock_output_cls.return_value.close.assert_not_called()   # output never started


def test_missing_credentials_is_clean_error():
    listener = FakeListener()
    session, events = make_session(listener)     # no client injected, no creds
    session.handle("hello")
    wait_idle(session)

    assert events[-1]["state"] == "error"
    assert "XAVIER_AIUI_EMAIL" in events[-1]["error"]
    assert listener.calls == ["pause", "resume"]


@patch("voice_chat.session.AudioOutput")
def test_overlapping_chat_dropped(mock_output_cls):
    gate = threading.Event()
    client = FakeClient(gate=gate)
    session, events = make_session(client=client)
    session.handle("first")
    session.handle("second")                     # dropped: session busy
    gate.set()
    wait_idle(session)

    assert len(client.chat_calls) == 1
    assert [e["state"] for e in events] == ["start", "end"]


@patch("voice_chat.session.AudioOutput")
def test_max_response_seconds_aborts_playback(mock_output_cls):
    class EndlessResp:
        def read(self, n):
            return b"\x00" * n

    class EndlessClient(FakeClient):
        def chat(self, text, conversation_id=None):
            return EndlessResp(), 24000, 1, None

    session, events = make_session(client=EndlessClient(),
                                   config={"max_response_seconds": 0})
    session.handle("hello")
    wait_idle(session)

    output = mock_output_cls.return_value
    output.abort.assert_called_once()
    output.close.assert_not_called()
    assert [e["state"] for e in events] == ["start", "end"]  # bounded, not an error
