"""
Hybrid recognizer: a grammar-constrained Vosk fast path for the fixed command
set, plus a Whisper accuracy path for open-vocabulary commands.

Routing is trigger-based and lives entirely in transcribe(), so the rest of the
pipeline (listener, activation policy, parser) is unchanged — it just receives
the best transcript. Vosk runs on every utterance (~200ms); if its result begins
with a trigger phrase ("open url", ...) the full audio is re-transcribed by
Whisper. A grammar non-match (empty / only "[unk]") is rejected outright, so
Whisper never runs on random speech.
"""

import logging

from core.parser import command_grammar, command_triggers, normalize_transcript
from stt.base import SpeechRecognizer, Transcript
from stt.vosk_recognizer import VoskRecognizer
from stt.whisper_recognizer import WhisperRecognizer

logger = logging.getLogger(__name__)


class HybridRecognizer(SpeechRecognizer):

    def __init__(self, stt_config, sample_rate=16000, wake_phrase=None):
        super().__init__(stt_config, sample_rate)
        self.wake = normalize_transcript(wake_phrase) if wake_phrase else None
        self.triggers = command_triggers()
        self.vosk = VoskRecognizer(
            stt_config.get("vosk", {}), sample_rate, grammar=command_grammar(wake_phrase)
        )
        self.whisper = WhisperRecognizer(stt_config.get("whisper", {}), sample_rate)
        self._whisper_ok = False

    def load(self):
        self.vosk.load()  # required; failure propagates to the factory fallback
        try:
            self.whisper.load()
            self._whisper_ok = True
        except Exception as e:
            logger.warning("Whisper accuracy path disabled (%s); fixed commands still work", e)

    def transcribe(self, pcm16, accurate=False):
        # Input mode forces the accuracy path: skip Vosk's grammar gate and trigger
        # routing and transcribe the whole utterance with Whisper. Silero VAD has
        # already gated to real speech upstream, so the reject step isn't needed.
        if accurate and self._whisper_ok:
            logger.info("hybrid: route=whisper (forced accurate)")
            return self.whisper.transcribe(pcm16)

        vt = self.vosk.transcribe(pcm16)

        # Reject out-of-grammar audio (empty or only unknown tokens) so the
        # Whisper path never runs on random speech. Check the raw Vosk text:
        # normalize_transcript() would strip the brackets off "[unk]".
        tokens = vt.text.split()
        if not tokens or all(t == "[unk]" for t in tokens):
            logger.info("hybrid: rejected (vosk: %r) — out of grammar", vt.text)
            return Transcript(text="", confidence=0.0)

        probe = normalize_transcript(vt.text)
        if self.wake and probe.startswith(self.wake + " "):
            probe = probe[len(self.wake) + 1:].strip()

        if self._whisper_ok and any(
            probe == t or probe.startswith(t + " ") for t in self.triggers
        ):
            logger.info("hybrid: route=whisper (vosk: %r)", vt.text)
            return self.whisper.transcribe(pcm16)

        logger.info("hybrid: route=vosk (%r)", vt.text)
        return vt

    def close(self):
        self.vosk.close()
        self.whisper.close()
