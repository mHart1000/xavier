"""
Config loader. Reads config.json (next to main.py), deep-merges over defaults,
and resolves relative model paths against the daemon directory so the daemon
works regardless of the launcher's working directory.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DAEMON_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = DAEMON_DIR.parent

DEFAULTS = {
    "stt": {
        "engine": "whisper",
        "fallback_engine": "vosk",
        "whisper": {"backend": "faster_whisper", "model": "base.en",
                    "model_path": "models/whisper", "compute_type": "int8",
                    "bias_to_commands": True},
        "vosk": {"model_path": "models/vosk-en"},
    },
    "audio": {"sample_rate": 16000, "channels": 1, "frame_ms": 32,
              "capture_source": None, "capture_command": None},
    "vad": {"engine": "silero", "model_path": "models/silero_vad.onnx", "threshold": 0.5},
    "listener": {
        "mode": "vad_continuous",
        "wake_phrase": "browser",
        "session_timeout_seconds": 300,
        "pre_roll_ms": 500,
        "min_speech_ms": 300,
        "end_silence_ms": 700,
        "max_segment_seconds": 8,
    },
    "safety": {
        "confirm_high_risk_commands": True,
        "allow_submit_actions": False,
        "allow_destructive_actions": False,
        "allow_continuous_commands_without_wake": True,
    },
    "protocol": {"native_messaging_host": "com.xavier.voice_browser"},
    "logging": {"level": "INFO", "file": "logs/xavier.log"},
}

# Config keys holding filesystem paths that should be resolved against DAEMON_DIR.
_PATH_KEYS = (
    ("stt", "whisper", "model_path"),
    ("stt", "vosk", "model_path"),
    ("vad", "model_path"),
)


def _deep_merge(base, override):
    """Recursively merge override into a copy of base."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_paths(config):
    """Make relative model paths absolute relative to the daemon directory."""
    for path in _PATH_KEYS:
        node = config
        for key in path[:-1]:
            node = node.get(key, {})
        leaf = path[-1]
        value = node.get(leaf)
        if value and not Path(value).is_absolute():
            node[leaf] = str(DAEMON_DIR / value)

    # The log file lives at the repo root (logs/xavier.log), not under daemon/.
    log_file = config.get("logging", {}).get("file")
    if log_file and not Path(log_file).is_absolute():
        config["logging"]["file"] = str(REPO_ROOT / log_file)
    return config


def load_config(path=None):
    """Load config.json merged over DEFAULTS. Missing file falls back to defaults."""
    config_path = Path(path) if path else DAEMON_DIR / "config.json"
    try:
        with open(config_path, encoding="utf-8") as f:
            user_config = json.load(f)
        config = _deep_merge(DEFAULTS, user_config)
    except FileNotFoundError:
        logger.warning("config.json not found at %s; using defaults", config_path)
        config = _deep_merge(DEFAULTS, {})
    except json.JSONDecodeError as e:
        logger.error("Invalid config.json (%s); using defaults", e)
        config = _deep_merge(DEFAULTS, {})

    return _resolve_paths(config)
