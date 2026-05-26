"""Recognizer factory: engine selection and fallback-on-load-failure."""

import pytest

import stt.base as base


class FakeRecognizer:
    def __init__(self, name):
        self.name = name
        self.loaded = False

    def load(self):
        self.loaded = True

    def transcribe(self, pcm16):
        return base.Transcript(text="", confidence=0.0)

    def close(self):
        pass


def test_unknown_engine_raises():
    with pytest.raises(ValueError):
        base.create_recognizer({"engine": "bogus"})


def test_falls_back_when_primary_load_fails(monkeypatch):
    def fake_build(engine, stt_config, sample_rate):
        if engine == "whisper":
            raise RuntimeError("whisper model missing")
        return FakeRecognizer(engine)

    monkeypatch.setattr(base, "_build", fake_build)

    recognizer = base.create_recognizer(
        {"engine": "whisper", "fallback_engine": "vosk"}
    )
    assert isinstance(recognizer, FakeRecognizer)
    assert recognizer.name == "vosk"
    assert recognizer.loaded


def test_no_fallback_reraises(monkeypatch):
    def fake_build(engine, stt_config, sample_rate):
        raise RuntimeError("boom")

    monkeypatch.setattr(base, "_build", fake_build)

    with pytest.raises(RuntimeError):
        base.create_recognizer({"engine": "whisper"})
