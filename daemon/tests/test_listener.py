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
