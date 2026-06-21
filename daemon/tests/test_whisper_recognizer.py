"""Whisper recognizer: command bias is applied for commands but dropped for
dictation, so dictated text keeps its natural casing and punctuation."""

from unittest.mock import MagicMock

from stt.whisper_recognizer import WhisperRecognizer


def make_recognizer():
    rec = WhisperRecognizer({"bias_to_commands": True})
    rec.hotwords = "click scroll url"
    rec.model = MagicMock()
    rec.model.transcribe.return_value = ([], None)
    return rec


def test_dictation_drops_command_hotwords():
    rec = make_recognizer()
    rec.transcribe(b"\x00\x00", accurate=True)
    assert rec.model.transcribe.call_args.kwargs["hotwords"] is None


def test_commands_keep_hotwords():
    rec = make_recognizer()
    rec.transcribe(b"\x00\x00", accurate=False)
    assert rec.model.transcribe.call_args.kwargs["hotwords"] == "click scroll url"
