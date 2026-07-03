"""
Vosk recognizer (Kaldi). Used two ways: unconstrained as a lightweight fallback
engine, and grammar-constrained as the fast path inside HybridRecognizer. Adapted
to the one-shot transcribe() contract: the whole utterance is fed at once and
FinalResult() is returned.
"""

import json
import logging

from stt.base import SpeechRecognizer, Transcript

logger = logging.getLogger(__name__)


class VoskRecognizer(SpeechRecognizer):

    def __init__(self, config, sample_rate=16000, grammar=None, wake_grammar=None):
        super().__init__(config, sample_rate)
        self.grammar = grammar
        self.wake_grammar = wake_grammar
        self.model = None
        self.recognizer = None
        self.wake_recognizer = None

    def load(self):
        from vosk import Model, KaldiRecognizer

        model_path = self.config.get("model_path", "models/vosk-en")
        logger.info("Loading Vosk model from %s", model_path)
        self.model = Model(model_path)
        if self.grammar is not None:
            self.recognizer = KaldiRecognizer(
                self.model, self.sample_rate, json.dumps(self.grammar)
            )
            logger.info("Vosk model loaded (grammar-constrained, %d tokens)", len(self.grammar))
        else:
            self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
            logger.info("Vosk model loaded")
        # Second recognizer shares the loaded Model, so it's cheap.
        if self.wake_grammar is not None:
            self.wake_recognizer = KaldiRecognizer(
                self.model, self.sample_rate, json.dumps(self.wake_grammar)
            )

    def transcribe(self, pcm16, accurate=False, wake_only=False):
        # No separate accuracy path; `accurate` is ignored.
        recognizer = self.recognizer
        if wake_only and self.wake_recognizer is not None:
            recognizer = self.wake_recognizer
        if recognizer is None:
            return Transcript(text="", confidence=0.0)

        recognizer.AcceptWaveform(pcm16)
        result = json.loads(recognizer.FinalResult())
        # Reset so the next utterance starts clean (no-op on older vosk).
        try:
            recognizer.Reset()
        except AttributeError:
            pass
        # Vosk gives no per-utterance confidence.
        return Transcript(text=result.get("text", ""), confidence=1.0)

    def close(self):
        self.recognizer = None
        self.wake_recognizer = None
        self.model = None
