"""Config loading: defaults, deep-merge, env credential overlay."""

import json

from core.config import load_config


def _clear_env(monkeypatch):
    monkeypatch.delenv("XAVIER_AIUI_EMAIL", raising=False)
    monkeypatch.delenv("XAVIER_AIUI_PASSWORD", raising=False)


def test_missing_file_uses_defaults(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    config = load_config(tmp_path / "nope.json")
    vc = config["voice_chat"]
    assert vc["enabled"] is False
    assert vc["email"] is None
    assert vc["password"] is None
    assert vc["base_url"] == "http://localhost:3000"
    assert config["listener"]["input_silence_timeout_seconds"] == 5


def test_env_overlays_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("XAVIER_AIUI_EMAIL", "env@example.com")
    monkeypatch.setenv("XAVIER_AIUI_PASSWORD", "sekrit")
    config = load_config(tmp_path / "nope.json")
    assert config["voice_chat"]["email"] == "env@example.com"
    assert config["voice_chat"]["password"] == "sekrit"


def test_env_beats_config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"voice_chat": {"email": "file@example.com"}}))
    monkeypatch.setenv("XAVIER_AIUI_EMAIL", "env@example.com")
    config = load_config(path)
    assert config["voice_chat"]["email"] == "env@example.com"


def test_empty_env_does_not_override(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"voice_chat": {"email": "file@example.com"}}))
    monkeypatch.setenv("XAVIER_AIUI_EMAIL", "")
    config = load_config(path)
    assert config["voice_chat"]["email"] == "file@example.com"


def test_defaults_not_polluted_across_loads(tmp_path, monkeypatch):
    # The env overlay must not mutate the DEFAULTS dict shared between loads.
    monkeypatch.setenv("XAVIER_AIUI_EMAIL", "env@example.com")
    load_config(tmp_path / "nope.json")
    _clear_env(monkeypatch)
    config = load_config(tmp_path / "nope.json")
    assert config["voice_chat"]["email"] is None
