"""Hybrid recognizer routing: Vosk fast path vs. Whisper accuracy path."""

from stt.base import Transcript
from stt.hybrid_recognizer import HybridRecognizer


class FakeRecognizer:
    def __init__(self, text="", confidence=1.0):
        self.result = Transcript(text=text, confidence=confidence)
        self.calls = 0
        self.last_accurate = None

    def transcribe(self, pcm16, accurate=False):
        self.calls += 1
        self.last_accurate = accurate
        return self.result

    def load(self):
        pass

    def close(self):
        pass


def make_hybrid(vosk_text, whisper_text="whisper output", whisper_ok=True, wake_phrase=None):
    h = HybridRecognizer({"vosk": {}, "whisper": {}}, 16000, wake_phrase)
    h.vosk = FakeRecognizer(text=vosk_text)
    h.whisper = FakeRecognizer(text=whisper_text)
    h._whisper_ok = whisper_ok
    return h


def test_fixed_command_uses_vosk():
    h = make_hybrid("scroll down")
    out = h.transcribe(b"")
    assert out.text == "scroll down"
    assert h.whisper.calls == 0


def test_trigger_routes_to_whisper():
    h = make_hybrid("open url example dot com", whisper_text="open url example dot com")
    out = h.transcribe(b"")
    assert h.whisper.calls == 1
    assert out.text == "open url example dot com"


def test_empty_vosk_rejected():
    h = make_hybrid("")
    out = h.transcribe(b"")
    assert out.text == ""
    assert h.whisper.calls == 0


def test_only_unk_rejected():
    h = make_hybrid("[unk] [unk]")
    out = h.transcribe(b"")
    assert out.text == ""
    assert h.whisper.calls == 0


def test_partial_unk_passes_through_to_vosk():
    h = make_hybrid("scroll [unk]")
    out = h.transcribe(b"")
    assert out.text == "scroll [unk]"
    assert h.whisper.calls == 0


def test_wake_prefixed_trigger_routes_to_whisper():
    h = make_hybrid(
        "browser open url example dot com",
        whisper_text="browser open url example dot com",
        wake_phrase="browser",
    )
    out = h.transcribe(b"")
    assert h.whisper.calls == 1
    assert out.text == "browser open url example dot com"


def test_confirm_word_passes_through_to_vosk():
    h = make_hybrid("confirm")
    out = h.transcribe(b"")
    assert out.text == "confirm"
    assert h.whisper.calls == 0


def test_trigger_falls_back_to_vosk_when_whisper_disabled():
    h = make_hybrid("open url example dot com", whisper_ok=False)
    out = h.transcribe(b"")
    assert h.whisper.calls == 0
    assert out.text == "open url example dot com"


def test_highlight_routes_to_whisper():
    # Vosk can only emit "highlight" + out-of-grammar tokens for the link text,
    # but that is enough to trigger the Whisper re-transcription.
    h = make_hybrid("highlight [unk] [unk]", whisper_text="highlight sign in")
    out = h.transcribe(b"")
    assert h.whisper.calls == 1
    assert out.text == "highlight sign in"


def test_accurate_forces_whisper_and_skips_vosk():
    # Input mode dictation: bypass the grammar gate and go straight to Whisper.
    h = make_hybrid("ignored", whisper_text="Don't forget the milk.")
    out = h.transcribe(b"", accurate=True)
    assert h.whisper.calls == 1
    assert h.vosk.calls == 0
    assert h.whisper.last_accurate is True   # no command bias → natural casing
    assert out.text == "Don't forget the milk."


def test_input_trigger_routes_to_whisper_as_dictation():
    # "input ..." is dictation, so Whisper runs without the command bias.
    h = make_hybrid("input [unk] [unk]", whisper_text="Buy the milk.")
    out = h.transcribe(b"")
    assert h.whisper.calls == 1
    assert h.whisper.last_accurate is True
    assert out.text == "Buy the milk."


def test_highlight_trigger_keeps_command_bias():
    h = make_hybrid("highlight [unk]", whisper_text="highlight sign in")
    h.transcribe(b"")
    assert h.whisper.last_accurate is False


def test_accurate_falls_back_to_vosk_when_whisper_disabled():
    h = make_hybrid("scroll down", whisper_ok=False)
    out = h.transcribe(b"", accurate=True)
    assert h.whisper.calls == 0
    assert out.text == "scroll down"
