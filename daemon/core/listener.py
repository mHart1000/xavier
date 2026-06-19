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
        listener_cfg = self.config["listener"]
        vad_cfg = self.config["vad"]
        sample_rate = self.config["audio"]["sample_rate"]

        # Build policy first so a bad listener mode fails before loading models.
        self.policy = ActivationPolicy(listener_cfg, self.config["safety"])

        self.recognizer = create_recognizer(
            self.config["stt"], sample_rate, wake_phrase=listener_cfg.get("wake_phrase")
        )

        self.vad = SileroVad(vad_cfg["model_path"], sample_rate, vad_cfg["threshold"])
        self.vad.load()

        # Models load once; the mic + worker thread are cycled by pause()/resume()
        # without paying for a reload.
        self._start_capture()
        logger.info("Listener started (mode=%s)", listener_cfg["mode"])

    def _start_capture(self):
        """Open the mic and spawn the worker thread, reusing loaded models.
        Shared by start() and resume()."""
        audio_cfg = self.config["audio"]
        listener_cfg = self.config["listener"]
        sample_rate = audio_cfg["sample_rate"]

        self._stop.clear()

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
            source=audio_cfg.get("capture_source"),    # None → system default
            command=audio_cfg.get("capture_command"),  # None → auto-detect tool
        )
        self.audio.start()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        threshold = self.config["vad"]["threshold"]
        sample_rate = self.config["audio"]["sample_rate"]
        frame_count = 0
        was_speech = False
        for frame in self.audio.frames():
            if self._stop.is_set():
                break

            prob = self.vad.is_speech(frame)
            is_speech = prob >= threshold
            frame_count += 1

            # Heartbeat every ~10 s so the user knows the pipeline is alive.
            if frame_count % 313 == 0:
                logger.debug("pipeline tick (vad=%.3f, threshold=%.2f)", prob, threshold)

            # Log when VAD transitions into speech so we can confirm audio is reaching the VAD.
            if is_speech and not was_speech:
                logger.info("VAD: speech start (prob=%.3f)", prob)
            was_speech = is_speech

            utterance = self.segmenter.feed(frame, is_speech)
            if utterance is None:
                continue

            duration_ms = len(utterance) // 2 / sample_rate * 1000
            logger.info("utterance collected (%.0f ms) — transcribing…", duration_ms)
            self.vad.reset()
            transcript = self.recognizer.transcribe(utterance)
            if not transcript.text:
                logger.info("empty transcript (utterance %.0f ms)", duration_ms)
                continue

            logger.info("transcript=%r (conf=%.2f)", transcript.text, transcript.confidence)
            command, reason = self.policy.evaluate(transcript.text, transcript.confidence)
            if command is not None:
                self.emit(command)
                logger.info("emitted %s (%s)", command["name"], reason)
            else:
                logger.info("transcript=%r rejected: %s", transcript.text, reason)

    def pause(self):
        """Release the mic and stop the worker thread, keeping models loaded so
        resume() is cheap. Safe to call when already paused."""
        self._stop.set()
        if self.audio is not None:
            self.audio.stop()
            self.audio = None
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None
        logger.info("Listener paused (mic released)")

    def resume(self):
        """Reopen the mic and restart the worker thread. No-op if already running."""
        if self.thread is not None and self.thread.is_alive():
            return
        self.vad.reset()
        self._start_capture()
        logger.info("Listener resumed")

    def stop(self):
        self.pause()
        if self.recognizer is not None:
            self.recognizer.close()
            self.recognizer = None
        logger.info("Listener stopped")
