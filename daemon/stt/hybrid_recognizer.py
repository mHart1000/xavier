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

from core.parser import (
    CONFIRM_WORDS,
    DEAFEN_WORD,
    INPUT_TRIGGER,
    LISTEN_WORD,
    command_grammar,
    command_triggers,
    normalize_transcript,
    parse_command,
    wake_grammar,
)
from stt.base import SpeechRecognizer, Transcript
from stt.vosk_recognizer import VoskRecognizer
from stt.whisper_recognizer import WhisperRecognizer

logger = logging.getLogger(__name__)


class HybridRecognizer(SpeechRecognizer):

    def __init__(self, stt_config, sample_rate=16000, wake_phrase=None):
        super().__init__(stt_config, sample_rate)
        self.wake = normalize_transcript(wake_phrase) if wake_phrase else None
        self.triggers = command_triggers()
        # Consumed by the activation policy, not parse_command; must not reroute.
        self._policy_words = frozenset(CONFIRM_WORDS) | {DEAFEN_WORD, LISTEN_WORD}
        self.vosk = VoskRecognizer(
            stt_config.get("vosk", {}), sample_rate,
            grammar=command_grammar(wake_phrase),
            wake_grammar=wake_grammar(wake_phrase) if wake_phrase else None,
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

    def transcribe(self, pcm16, accurate=False, wake_only=False):
        # Deafened: Vosk-only, wake grammar; [unk] noise is stripped so the exact phrase still matches.
        if wake_only:
            vt = self.vosk.transcribe(pcm16, wake_only=True)
            text = " ".join(t for t in vt.text.split() if t != "[unk]")
            logger.info("hybrid: route=vosk-wake (%r)", vt.text)
            return Transcript(text=text, confidence=vt.confidence if text else 0.0)

        # Input mode forces the accuracy path: skip Vosk's grammar gate and trigger
        # routing and transcribe the whole utterance with Whisper. Silero VAD has
        # already gated to real speech upstream, so the reject step isn't needed.
        if accurate and self._whisper_ok:
            logger.info("hybrid: route=whisper (forced accurate)")
            return self.whisper.transcribe(pcm16, accurate=True)

        vt = self.vosk.transcribe(pcm16)

        # Reject out-of-grammar audio (empty or only unknown tokens) so the
        # Whisper path never runs on random speech. Check the raw Vosk text:
        # normalize_transcript() would strip the brackets off "[unk]".
        tokens = vt.text.split()
        if not tokens or all(t == "[unk]" for t in tokens):
            logger.info("hybrid: rejected (vosk: %r) — out of grammar", vt.text)
            return Transcript(text="", confidence=0.0)

        probe = normalize_transcript(vt.text)
        wake_stripped = False
        if self.wake and probe.startswith(self.wake + " "):
            probe = probe[len(self.wake) + 1:].strip()
            wake_stripped = True

        if self._whisper_ok:
            matched = next(
                (t for t in self.triggers if probe == t or probe.startswith(t + " ")), None
            )
            if matched is not None:
                # "input" is dictation (natural casing); other triggers are commands.
                logger.info("hybrid: route=whisper (vosk: %r)", vt.text)
                return self.whisper.transcribe(pcm16, accurate=(matched == INPUT_TRIGGER))

        # Wake + non-command remainder: Vosk confirmed the wake word, so re-transcribe
        # the full audio for the voice-chat path. wake_heard tells downstream the wake
        # is real even if Whisper spells it differently.
        if wake_stripped and self._whisper_ok and probe not in self._policy_words:
            if "[unk]" in tokens or parse_command(probe) is None:
                logger.info("hybrid: route=whisper (wake reroute, vosk: %r)", vt.text)
                wt = self.whisper.transcribe(pcm16, accurate=True)
                return Transcript(text=wt.text, confidence=wt.confidence, wake_heard=True)

        logger.info("hybrid: route=vosk (%r)", vt.text)
        return vt

    def close(self):
        self.vosk.close()
        self.whisper.close()
