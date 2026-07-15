"""AudioOutput subprocess lifecycle, using harmless commands instead of audio tools."""

import shutil

import pytest

from audio.output import AudioOutput, _default_playback_command


def test_write_and_close_drains():
    # `cat` consumes stdin like a player would; returncode 0 means clean drain.
    out = AudioOutput(16000, 1, command=["cat"])
    out.start()
    proc = out.proc
    out.write(b"\x00\x01" * 256)
    out.close()
    assert proc.returncode == 0
    assert out.proc is None


def test_abort_kills_immediately():
    out = AudioOutput(16000, 1, command=["cat"])
    out.start()
    proc = out.proc
    out.abort()
    assert proc.returncode is not None
    assert out.proc is None


def test_close_and_abort_are_idempotent():
    out = AudioOutput(16000, 1, command=["cat"])
    out.start()
    out.close()
    out.close()
    out.abort()


def test_write_after_player_death_raises():
    out = AudioOutput(16000, 1, command=["true"])   # exits immediately
    out.start()
    out.proc.wait(timeout=5)
    with pytest.raises(RuntimeError, match="died"):
        for _ in range(64):                          # first write may land in the pipe
            out.write(b"\x00" * 4096)
    out.abort()


def _which_only(*names):
    return lambda name: f"/usr/bin/{name}" if name in names else None


def test_default_command_prefers_paplay(monkeypatch):
    monkeypatch.setattr(shutil, "which", _which_only("paplay", "pw-play", "pw-cat"))
    cmd = _default_playback_command(24000, 1)
    assert cmd == ["paplay", "--raw", "--rate=24000", "--channels=1", "--format=s16le"]


def test_default_command_falls_back_to_pw_play(monkeypatch):
    monkeypatch.setattr(shutil, "which", _which_only("pw-play", "pw-cat"))
    cmd = _default_playback_command(24000, 2)
    assert cmd == ["pw-play", "--rate", "24000", "--channels", "2",
                   "--format", "s16", "-"]


def test_default_command_falls_back_to_pw_cat(monkeypatch):
    monkeypatch.setattr(shutil, "which", _which_only("pw-cat"))
    assert _default_playback_command(24000, 1)[:2] == ["pw-cat", "--playback"]


def test_no_tool_found_raises(monkeypatch):
    monkeypatch.setattr(shutil, "which", _which_only())
    with pytest.raises(RuntimeError, match="playback_command"):
        _default_playback_command(24000, 1)


def test_explicit_command_skips_probe(monkeypatch):
    monkeypatch.setattr(shutil, "which", _which_only())
    out = AudioOutput(16000, 1, command=["cat"])
    out.start()
    out.abort()
