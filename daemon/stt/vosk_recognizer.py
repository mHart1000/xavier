"""
Vosk recognizer (Kaldi). Kept as a lightweight fallback engine. Migrated from
the old core/stt_interface.py and adapted to the one-shot transcribe() contract:
the whole utterance is fed at once and FinalResult() is returned.
"""

import json
import logging

from stt.base import SpeechRecognizer, Transcript

logger = logging.getLogger(__name__)


class VoskRecognizer(SpeechRecognizer):

    def __init__(self, config, sample_rate=16000):
        super().__init__(config, sample_rate)
        self.model = None
        self.recognizer = None

    def load(self):
        from vosk import Model, KaldiRecognizer

        model_path = self.config.get("model_path", "models/vosk-en")
        logger.info("Loading Vosk model from %s", model_path)
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
        logger.info("Vosk model loaded")

    def transcribe(self, pcm16):
        if self.recognizer is None:
            return Transcript(text="", confidence=0.0)

        self.recognizer.AcceptWaveform(pcm16)
        result = json.loads(self.recognizer.FinalResult())
        # Reset so the next utterance starts clean (no-op on older vosk).
        try:
            self.recognizer.Reset()
        except AttributeError:
            pass
        # Vosk gives no per-utterance confidence.
        return Transcript(text=result.get("text", ""), confidence=1.0)

    def close(self):
        self.recognizer = None
        self.model = None
