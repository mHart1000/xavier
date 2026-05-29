"""
Activation policy. Sits between the recognizer and the parser:

- strips the wake phrase (wake is policy, not grammar) and manages session state
- runs the deterministic parser on the cleaned transcript
- enforces risk tiers: LOW/MEDIUM allowed in an active session, HIGH requires a
  spoken "confirm" first (when confirm_high_risk_commands is set)

evaluate() returns (command_or_None, reason). The listener emits the command if
present and logs the reason either way.

Implemented modes: vad_continuous, push_to_talk. Wake/session modes are stubbed
and rejected at construction so misconfiguration fails fast at startup.
"""

import logging
import time

from core.parser import CONFIRM_WORDS, normalize_transcript, parse_command

logger = logging.getLogger(__name__)

IMPLEMENTED_MODES = ("vad_continuous", "push_to_talk")
STUBBED_MODES = ("wake_required", "wake_then_session", "adaptive_wake")

CONFIRM_TIMEOUT_SECONDS = 15

LOW_RISK = frozenset({
    "scroll_up", "scroll_down", "page_up", "page_down",
    "jump_top", "jump_bottom", "hints_show", "hints_hide", "focus_page",
})
MEDIUM_RISK = frozenset({
    "nav_back", "nav_forward", "nav_reload",
    "tab_new", "tab_next", "tab_prev", "hint_click", "focus_address",
})
HIGH_RISK = frozenset({"tab_close", "open_url"})


def risk_tier(name):
    if name in LOW_RISK:
        return "low"
    if name in MEDIUM_RISK:
        return "medium"
    if name in HIGH_RISK:
        return "high"
    return "medium"  # unknown commands treated cautiously


class ActivationPolicy:

    def __init__(self, listener_config, safety_config):
        self.mode = listener_config.get("mode", "vad_continuous")
        if self.mode in STUBBED_MODES:
            raise NotImplementedError(
                f"Listener mode '{self.mode}' is not implemented yet "
                f"(available: {', '.join(IMPLEMENTED_MODES)})"
            )
        if self.mode not in IMPLEMENTED_MODES:
            raise ValueError(f"Unknown listener mode: {self.mode}")

        self.wake_phrase = normalize_transcript(listener_config.get("wake_phrase", "browser"))
        self.session_timeout = listener_config.get("session_timeout_seconds", 300)
        self.confirm_high = safety_config.get("confirm_high_risk_commands", True)
        self.allow_continuous = safety_config.get("allow_continuous_commands_without_wake", True)

        self.session_active_until = 0.0
        self.pending_command = None
        self.pending_until = 0.0

    def _touch_session(self, now):
        self.session_active_until = now + self.session_timeout

    def _session_active(self, now):
        return now < self.session_active_until

    def evaluate(self, transcript, confidence=1.0, now=None):
        now = time.monotonic() if now is None else now
        text = normalize_transcript(transcript)
        if not text:
            return None, "empty"

        # Expire a stale pending confirmation.
        if self.pending_command is not None and now >= self.pending_until:
            self.pending_command = None

        # Confirmation flow takes priority.
        if self.pending_command is not None:
            if text in CONFIRM_WORDS:
                command = self.pending_command
                self.pending_command = None
                self._touch_session(now)
                return command, "confirmed"
            self.pending_command = None  # any other utterance cancels

        session_ok = self._session_active(now)

        if self.mode == "push_to_talk":
            # Capture is gated externally; treat each utterance as in-session.
            session_ok = True
        else:  # vad_continuous
            if self.wake_phrase and text == self.wake_phrase:
                self._touch_session(now)
                return None, "wake_only"
            if self.wake_phrase and text.startswith(self.wake_phrase + " "):
                text = text[len(self.wake_phrase) + 1:].strip()
                self._touch_session(now)
                session_ok = True
            elif self.allow_continuous:
                session_ok = True
            elif not session_ok:
                return None, "no_session"

        command = parse_command(text, confidence)
        if command is None:
            return None, "no_match"

        tier = risk_tier(command["name"])
        if not session_ok:
            return None, f"{tier}_no_session"

        if tier == "high" and self.confirm_high:
            self.pending_command = command
            self.pending_until = now + CONFIRM_TIMEOUT_SECONDS
            return None, "await_confirm"

        self._touch_session(now)
        return command, "ok"
