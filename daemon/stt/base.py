"""
Speech recognizer abstraction. Engines take a complete utterance (16 kHz mono
int16 PCM) and return a transcript. The segmenter upstream decides utterance
boundaries, so engines are one-shot rather than streaming.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Transcript:
    text: str
    confidence: float


class SpeechRecognizer:
    """Base class for STT engines."""

    def __init__(self, config, sample_rate=16000):
        self.config = config
        self.sample_rate = sample_rate

    def load(self):
        """Load the model. Heavy; called once at startup."""
        raise NotImplementedError

    def transcribe(self, pcm16):
        """Transcribe one utterance (int16 PCM bytes). Returns Transcript."""
        raise NotImplementedError

    def close(self):
        """Release resources."""


def _build(engine, stt_config, sample_rate, wake_phrase=None):
    if engine == "whisper":
        from stt.whisper_recognizer import WhisperRecognizer
        return WhisperRecognizer(stt_config.get("whisper", {}), sample_rate)
    if engine == "vosk":
        from stt.vosk_recognizer import VoskRecognizer
        return VoskRecognizer(stt_config.get("vosk", {}), sample_rate)
    if engine == "hybrid":
        from stt.hybrid_recognizer import HybridRecognizer
        return HybridRecognizer(stt_config, sample_rate, wake_phrase)
    raise ValueError(f"Unknown STT engine: {engine}")


def create_recognizer(stt_config, sample_rate=16000, wake_phrase=None):
    """
    Build and load the configured recognizer. If the primary engine fails to
    load (e.g. model missing), fall back to stt_config['fallback_engine'].
    wake_phrase is threaded through for the hybrid engine's grammar.
    """
    engine = stt_config.get("engine", "whisper")
    fallback = stt_config.get("fallback_engine")

    try:
        recognizer = _build(engine, stt_config, sample_rate, wake_phrase)
        recognizer.load()
        logger.info("STT engine ready: %s", engine)
        return recognizer
    except Exception as e:
        logger.error("Primary STT '%s' failed to load: %s", engine, e)
        if not fallback or fallback == engine:
            raise
        logger.info("Falling back to STT engine: %s", fallback)
        recognizer = _build(fallback, stt_config, sample_rate, wake_phrase)
        recognizer.load()
        return recognizer
