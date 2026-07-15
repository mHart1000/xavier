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
import time

from audio.input import AudioInput
from audio.segmenter import Segmenter
from audio.vad import SileroVad, window_size
from core.activation_policy import ActivationPolicy
from stt.base import create_recognizer

logger = logging.getLogger(__name__)


class Listener:

    def __init__(self, config, emit_command, emit_event=None, on_voice_chat=None):
        self.config = config
        self.emit = emit_command
        # Sends non-command messages (input_mode status); no-op if unset.
        self.emit_event = emit_event or (lambda event: None)
        # Daemon-internal voice_chat intents go here, never to the extension.
        self.on_voice_chat = on_voice_chat
        self.audio = None
        self.vad = None
        self.segmenter = None
        self.recognizer = None
        self.policy = None
        self.thread = None
        self._input_mode_prev = False
        self._confirm_prev = None
        self._deafened_prev = False
        self._stop = threading.Event()
        self._closed = False

    @property
    def state(self):
        """Current listening state: "off" (mic released), "deafened", or "listening"."""
        if self.audio is None:
            return "off"
        if self.policy is not None and self.policy.deafened:
            return "deafened"
        return "listening"

    def _emit_state(self):
        self.emit_event({"type": "listening_state", "state": self.state})

    def start(self):
        listener_cfg = self.config["listener"]
        vad_cfg = self.config["vad"]
        sample_rate = self.config["audio"]["sample_rate"]

        # Build policy first so a bad listener mode fails before loading models.
        self.policy = ActivationPolicy(listener_cfg, self.config["safety"],
                                       self.config.get("voice_chat"))

        self.recognizer = create_recognizer(
            self.config["stt"], sample_rate, wake_phrase=listener_cfg.get("wake_phrase")
        )

        self.vad = SileroVad(vad_cfg["model_path"], sample_rate, vad_cfg["threshold"])
        self.vad.load()

        # Models load once; the mic + worker thread are cycled by pause()/resume()
        # without paying for a reload.
        self._start_capture()
        self._emit_state()
        logger.info("Listener started (mode=%s)", listener_cfg["mode"])

    def _start_capture(self):
        """Open the mic and spawn the worker thread, reusing loaded models.
        Shared by start() and resume()."""
        audio_cfg = self.config["audio"]
        listener_cfg = self.config["listener"]
        sample_rate = audio_cfg["sample_rate"]

        self._stop.clear()
        self._input_mode_prev = False
        self._confirm_prev = None
        self._deafened_prev = self.policy.deafened

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

    def _sync_input_mode_indicator(self):
        """Emit an input_mode status event when the mode flips. Called each frame,
        so it catches every cause: utterance, silence timeout, or external exit."""
        active = self.policy.in_input_mode
        if active != self._input_mode_prev:
            self._input_mode_prev = active
            self.emit_event({"type": "input_mode", "state": "start" if active else "end"})

    def _sync_confirm_indicator(self):
        """Emit a confirm event when a high-risk command starts or stops awaiting a
        spoken 'confirm'. Called each frame, so it also fires the 'end' when the
        confirm window times out with no further utterance."""
        pending = self.policy.confirm_pending()
        if pending != self._confirm_prev:
            self._confirm_prev = pending
            if pending:
                self.emit_event({"type": "confirm", "state": "start", "command": pending})
            else:
                self.emit_event({"type": "confirm", "state": "end"})

    def _sync_listening_state_indicator(self):
        """Emit a listening_state event when the deafened flag flips. Called each
        frame so voice- and extension-initiated flips are both announced."""
        deafened = self.policy.deafened
        if deafened != self._deafened_prev:
            self._deafened_prev = deafened
            self._emit_state()

    def _run(self):
        threshold = self.config["vad"]["threshold"]
        sample_rate = self.config["audio"]["sample_rate"]
        frame_count = 0
        was_speech = False
        for frame in self.audio.frames():
            if self._stop.is_set():
                break

            self._sync_input_mode_indicator()
            self._sync_confirm_indicator()
            self._sync_listening_state_indicator()

            prob = self.vad.is_speech(frame)
            is_speech = prob >= threshold
            frame_count += 1

            # Input mode: hold it open while speech continues, auto-exit on silence.
            if self.policy.in_input_mode:
                now = time.monotonic()
                if is_speech:
                    self.policy.refresh_input_activity(now)
                elif self.policy.input_expired(now):
                    self.policy.exit_input_mode()
                    logger.info("input mode ended (%ss silence)", self.policy.input_silence_timeout)

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
            transcript = self.recognizer.transcribe(
                utterance, accurate=self.policy.in_input_mode, wake_only=self.policy.deafened
            )
            if not transcript.text:
                logger.info("empty transcript (utterance %.0f ms)", duration_ms)
                continue

            logger.info("transcript=%r (conf=%.2f)", transcript.text, transcript.confidence)
            command, reason = self.policy.evaluate(
                transcript.text, transcript.confidence, wake_heard=transcript.wake_heard
            )
            if command is None:
                logger.info("transcript=%r rejected: %s", transcript.text, reason)
            elif command["name"] == "voice_chat":
                # Daemon-internal: never sent to the extension. The callback only
                # spawns the session thread — pause() joins this worker, no self-join.
                if self.on_voice_chat is not None:
                    logger.info("voice chat intent (%s): %r", reason, command["args"]["text"])
                    self.on_voice_chat(command["args"]["text"])
                else:
                    logger.info("voice chat intent dropped (no handler): %r",
                                command["args"]["text"])
            else:
                self.emit(command)
                logger.info("emitted %s (%s)", command["name"], reason)

    def pause(self):
        """Release the mic and stop the worker thread, keeping models loaded so
        resume() is cheap. Safe to call when already paused."""
        was_running = self.audio is not None
        self._stop.set()
        if self.audio is not None:
            self.audio.stop()
            self.audio = None
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None
        # Worker stopped, so emit the input_mode "end" here if it was still active.
        if self.policy is not None and self.policy.exit_input_mode():
            self._input_mode_prev = False
            self.emit_event({"type": "input_mode", "state": "end"})
        # Likewise clear a dangling confirm prompt so releasing the mic doesn't strand it.
        if self.policy is not None:
            self.policy.clear_pending_confirm()
        if self._confirm_prev is not None:
            self._confirm_prev = None
            self.emit_event({"type": "confirm", "state": "end"})
        if was_running:
            self._emit_state()
        logger.info("Listener paused (mic released)")

    def resume(self):
        """Reopen the mic and restart the worker thread. No-op if already running
        or after stop() — a late voice-chat resume must not re-open the mic."""
        if self._closed:
            return
        if self.thread is not None and self.thread.is_alive():
            return
        self.vad.reset()
        self._start_capture()
        self._emit_state()
        logger.info("Listener resumed")

    def set_state(self, state):
        """Apply a listening state ("listening" | "deafened" | "off") requested by
        the extension. Idempotent. The deafened flag is set before resume() so the
        (re)start announces the right state; deafened<->listening flips while
        already running are announced by the frame-loop sync instead."""
        if state == "off":
            self.pause()
            return
        if self.policy is not None:
            self.policy.set_deafened(state == "deafened")
        self.resume()

    def exit_input_mode(self):
        """External request to leave input mode (e.g. the extension's exit hotkey).
        The worker loop emits the 'end' status on its next tick."""
        if self.policy is not None:
            self.policy.exit_input_mode()

    def stop(self):
        self._closed = True
        self.pause()
        if self.recognizer is not None:
            self.recognizer.close()
            self.recognizer = None
        logger.info("Listener stopped")
