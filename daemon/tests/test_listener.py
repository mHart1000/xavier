"""Listener pause/resume lifecycle, with the heavy pieces (STT, VAD, mic) mocked.

The mocked AudioInput yields no frames, so the worker thread exits immediately;
these tests assert the mic/thread/recognizer wiring, not the speech pipeline.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.listener import Listener


def make_config():
    return {
        "audio": {"sample_rate": 16000, "channels": 1, "frame_ms": 32},
        "vad": {"model_path": "vad.onnx", "threshold": 0.5},
        "listener": {
            "mode": "always_on",
            "pre_roll_ms": 200,
            "min_speech_ms": 300,
            "end_silence_ms": 300,
            "max_segment_seconds": 10,
        },
        "safety": {},
        "stt": {},
    }


@pytest.fixture
def listener():
    with patch("core.listener.create_recognizer") as create_rec, \
         patch("core.listener.SileroVad"), \
         patch("core.listener.Segmenter"), \
         patch("core.listener.ActivationPolicy"), \
         patch("core.listener.AudioInput") as audio_cls:

        def make_audio(*args, **kwargs):
            inst = MagicMock()
            inst.frames.return_value = iter(())  # worker thread exits at once
            return inst
        audio_cls.side_effect = make_audio

        obj = Listener(make_config(), emit_command=MagicMock())
        obj._audio_cls = audio_cls
        obj._create_rec = create_rec
        yield obj
        obj.stop()


def test_start_opens_mic_and_thread(listener):
    listener.start()
    assert listener._audio_cls.call_count == 1
    listener.audio.start.assert_called_once()
    assert listener.thread is not None


def test_pause_releases_mic_and_keeps_models(listener):
    listener.start()
    audio = listener.audio
    recognizer = listener.recognizer

    listener.pause()

    audio.stop.assert_called_once()       # mic released
    assert listener.audio is None
    assert listener.thread is None
    recognizer.close.assert_not_called()  # models stay loaded


def test_resume_reopens_mic_without_reloading_models(listener):
    listener.start()
    listener.pause()

    listener.resume()

    assert listener._audio_cls.call_count == 2  # new mic
    assert listener.audio is not None
    assert listener._create_rec.call_count == 1  # recognizer reused, not rebuilt


def test_resume_while_running_is_noop(listener):
    listener.start()
    listener.thread = MagicMock(is_alive=MagicMock(return_value=True))
    before = listener._audio_cls.call_count

    listener.resume()

    assert listener._audio_cls.call_count == before  # no second mic opened


def test_repeated_toggle_is_stable(listener):
    listener.start()
    for _ in range(5):
        listener.pause()
        listener.resume()

    assert listener.audio is not None
    listener.pause()
    assert listener.audio is None


def test_stop_closes_recognizer(listener):
    listener.start()
    recognizer = listener.recognizer

    listener.stop()

    recognizer.close.assert_called_once()
    assert listener.audio is None


def test_input_mode_indicator_emits_on_transition():
    events = []
    lis = Listener(make_config(), emit_command=lambda c: None, emit_event=events.append)
    lis.policy = SimpleNamespace(in_input_mode=False)

    lis._sync_input_mode_indicator()
    assert events == []                       # no change → no event

    lis.policy.in_input_mode = True
    lis._sync_input_mode_indicator()
    lis._sync_input_mode_indicator()          # idempotent while active
    assert events == [{"type": "input_mode", "state": "start"}]

    lis.policy.in_input_mode = False
    lis._sync_input_mode_indicator()
    assert events[-1] == {"type": "input_mode", "state": "end"}


def test_confirm_indicator_emits_on_transition():
    events = []
    lis = Listener(make_config(), emit_command=lambda c: None, emit_event=events.append)
    lis.policy = SimpleNamespace(confirm_pending=lambda: None)

    lis._sync_confirm_indicator()
    assert events == []                       # nothing pending → no event

    lis.policy.confirm_pending = lambda: "tab_close"
    lis._sync_confirm_indicator()
    lis._sync_confirm_indicator()             # idempotent while pending
    assert events == [{"type": "confirm", "state": "start", "command": "tab_close"}]

    lis.policy.confirm_pending = lambda: None
    lis._sync_confirm_indicator()
    assert events[-1] == {"type": "confirm", "state": "end"}


def test_exit_input_mode_delegates_to_policy():
    lis = Listener(make_config(), emit_command=lambda c: None)
    lis.policy = MagicMock()
    lis.exit_input_mode()
    lis.policy.exit_input_mode.assert_called_once()


def test_state_property():
    lis = Listener(make_config(), emit_command=lambda c: None)
    assert lis.state == "off"                 # no mic yet
    lis.policy = SimpleNamespace(deafened=False)
    lis.audio = object()
    assert lis.state == "listening"
    lis.policy.deafened = True
    assert lis.state == "deafened"


def test_set_state_off_pauses(listener):
    listener.start()
    listener.set_state("off")
    assert listener.audio is None


def test_set_state_deafened_sets_policy_and_resumes(listener):
    listener.start()
    listener.set_state("off")
    listener.set_state("deafened")
    listener.policy.set_deafened.assert_called_with(True)
    assert listener.audio is not None


def test_set_state_listening_clears_deafened(listener):
    listener.start()
    listener.set_state("listening")
    listener.policy.set_deafened.assert_called_with(False)
    assert listener.audio is not None


def test_pause_emits_listening_state_off_once(listener):
    events = []
    listener.emit_event = events.append
    listener.start()

    listener.pause()
    offs = [e for e in events if e["type"] == "listening_state" and e["state"] == "off"]
    assert len(offs) == 1

    listener.pause()                          # already paused: no re-emit
    offs = [e for e in events if e["type"] == "listening_state" and e["state"] == "off"]
    assert len(offs) == 1


def test_voice_chat_command_routes_to_callback():
    from stt.base import Transcript

    emit_command = MagicMock()
    on_voice_chat = MagicMock()

    with patch("core.listener.create_recognizer") as create_rec, \
         patch("core.listener.SileroVad") as vad_cls, \
         patch("core.listener.Segmenter") as seg_cls, \
         patch("core.listener.ActivationPolicy") as policy_cls, \
         patch("core.listener.AudioInput") as audio_cls:

        vad_cls.return_value.is_speech.return_value = 1.0  # real float for >= threshold
        audio = MagicMock()
        audio.frames.return_value = iter([b"\x00" * 1024])
        audio_cls.return_value = audio

        seg = MagicMock()
        seg.feed.return_value = b"\x00" * 3200
        seg_cls.return_value = seg

        recognizer = MagicMock()
        recognizer.transcribe.return_value = Transcript(
            text="Browser, hello there.", confidence=0.9, wake_heard=True)
        create_rec.return_value = recognizer

        policy = MagicMock()
        policy.in_input_mode = False
        policy.deafened = False
        policy.confirm_pending.return_value = None
        policy.evaluate.return_value = (
            {"type": "command", "name": "voice_chat", "args": {"text": "hello there."}},
            "chat",
        )
        policy_cls.return_value = policy

        lis = Listener(make_config(), emit_command, on_voice_chat=on_voice_chat)
        lis.start()
        lis.thread.join(timeout=5)

        on_voice_chat.assert_called_once_with("hello there.")
        emit_command.assert_not_called()
        assert policy.evaluate.call_args.kwargs["wake_heard"] is True
        lis.stop()


def test_resume_after_stop_is_noop(listener):
    listener.start()
    listener.stop()
    before = listener._audio_cls.call_count

    listener.resume()

    assert listener._audio_cls.call_count == before  # mic stays closed
    assert listener.audio is None


def test_listening_state_indicator_emits_on_transition():
    events = []
    lis = Listener(make_config(), emit_command=lambda c: None, emit_event=events.append)
    lis.policy = SimpleNamespace(deafened=False)
    lis.audio = object()                      # mic "open" so state derives from the flag

    lis._sync_listening_state_indicator()
    assert events == []                       # no change → no event

    lis.policy.deafened = True
    lis._sync_listening_state_indicator()
    lis._sync_listening_state_indicator()     # idempotent while deafened
    assert events == [{"type": "listening_state", "state": "deafened"}]

    lis.policy.deafened = False
    lis._sync_listening_state_indicator()
    assert events[-1] == {"type": "listening_state", "state": "listening"}
