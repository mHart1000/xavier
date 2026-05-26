"""
Listener: the speech pipeline on a worker thread.

  AudioInput -> SileroVad -> Segmenter -> SpeechRecognizer
            -> ActivationPolicy -> (parser) -> emit_command

start() loads the recognizer + VAD (heavy, once), opens the mic, and spawns the
worker thread. stop() tears down the stream and joins the thread so the mic is
released when Firefox closes the Native Messaging port.
"""

import logging
import threading

from audio.input import AudioInput
from audio.segmenter import Segmenter
from audio.vad import SileroVad, window_size
from core.activation_policy import ActivationPolicy
from stt.base import create_recognizer

logger = logging.getLogger(__name__)


class Listener:

    def __init__(self, config, emit_command):
        self.config = config
        self.emit = emit_command
        self.audio = None
        self.vad = None
        self.segmenter = None
        self.recognizer = None
        self.policy = None
        self.thread = None
        self._stop = threading.Event()

    def start(self):
        audio_cfg = self.config["audio"]
        vad_cfg = self.config["vad"]
        listener_cfg = self.config["listener"]
        sample_rate = audio_cfg["sample_rate"]

        # Build policy first so a bad listener mode fails before loading models.
        self.policy = ActivationPolicy(listener_cfg, self.config["safety"])

        self.recognizer = create_recognizer(self.config["stt"], sample_rate)

        self.vad = SileroVad(vad_cfg["model_path"], sample_rate, vad_cfg["threshold"])
        self.vad.load()

        self.segmenter = Segmenter(
            sample_rate=sample_rate,
            frame_ms=audio_cfg.get("frame_ms", 32),
            pre_roll_ms=listener_cfg["pre_roll_ms"],
            min_speech_ms=listener_cfg["min_speech_ms"],
            end_silence_ms=listener_cfg["end_silence_ms"],
            max_segment_seconds=listener_cfg["max_segment_seconds"],
        )

        # Frame size == VAD window so each frame is one VAD step.
        self.audio = AudioInput(
            sample_rate=sample_rate,
            channels=audio_cfg["channels"],
            frame_samples=window_size(sample_rate),
        )
        self.audio.start()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("Listener started (mode=%s)", listener_cfg["mode"])

    def _run(self):
        threshold = self.config["vad"]["threshold"]
        for frame in self.audio.frames():
            if self._stop.is_set():
                break

            is_speech = self.vad.is_speech(frame) >= threshold
            utterance = self.segmenter.feed(frame, is_speech)
            if utterance is None:
                continue

            self.vad.reset()
            transcript = self.recognizer.transcribe(utterance)
            if not transcript.text:
                logger.debug("empty transcript")
                continue

            command, reason = self.policy.evaluate(transcript.text, transcript.confidence)
            if command is not None:
                self.emit(command)
                logger.info("emitted %s (%s)", command["name"], reason)
            else:
                logger.info("transcript=%r rejected: %s", transcript.text, reason)

    def stop(self):
        self._stop.set()
        if self.audio is not None:
            self.audio.stop()
        if self.thread is not None:
            self.thread.join(timeout=2)
        if self.recognizer is not None:
            self.recognizer.close()
        logger.info("Listener stopped")
