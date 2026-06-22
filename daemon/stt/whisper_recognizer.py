"""
Whisper recognizer via faster-whisper (CTranslate2). CPU + int8 by default,
no PyTorch. The model is fetched into model_path on first use, then loaded
locally on subsequent runs (one-time network access at setup).
"""

import logging

import numpy as np

from core.parser import command_hotwords
from stt.base import SpeechRecognizer, Transcript

logger = logging.getLogger(__name__)


class WhisperRecognizer(SpeechRecognizer):

    def __init__(self, config, sample_rate=16000):
        super().__init__(config, sample_rate)
        self.model = None
        # Bias decoding toward the command vocabulary (e.g. "scroll" not "stroll").
        self.hotwords = command_hotwords() if config.get("bias_to_commands", True) else None

    def load(self):
        from faster_whisper import WhisperModel

        model = self.config.get("model", "base.en")
        model_path = self.config.get("model_path")
        compute_type = self.config.get("compute_type", "int8")

        logger.info("Loading faster-whisper model '%s' (compute_type=%s)", model, compute_type)
        # download_root keeps the model inside the project; first run may download.
        self.model = WhisperModel(
            model, device="cpu", compute_type=compute_type, download_root=model_path
        )
        logger.info("faster-whisper model loaded")

    def transcribe(self, pcm16, accurate=False):
        if self.model is None:
            return Transcript(text="", confidence=0.0)

        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        # The command bias is a lowercase, unpunctuated prompt and Whisper mimics
        # that style; drop it for dictation to keep natural casing/punctuation.
        hotwords = None if accurate else self.hotwords
        segments, _info = self.model.transcribe(
            audio, language="en", beam_size=1, condition_on_previous_text=False,
            hotwords=hotwords,
        )

        texts, logprobs = [], []
        for seg in segments:
            texts.append(seg.text)
            logprobs.append(seg.avg_logprob)

        text = " ".join(texts).strip()
        confidence = float(np.exp(np.mean(logprobs))) if logprobs else 0.0
        return Transcript(text=text, confidence=confidence)

    def close(self):
        self.model = None
