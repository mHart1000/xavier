"""
Activation policy. Sits between the recognizer and the parser:

- strips the wake phrase (wake is policy, not grammar) and manages session state
- runs the deterministic parser on the cleaned transcript
- enforces risk tiers: LOW/MEDIUM allowed in an active session, HIGH requires a
  spoken "confirm" first (when confirm_high_risk_commands is set)
- routes wake-prefixed free-form speech to a daemon-internal voice_chat intent
  (reason "chat") when voice chat is enabled

evaluate() returns (command_or_None, reason). The listener emits the command if
present and logs the reason either way.

Implemented modes: vad_continuous, push_to_talk. Wake/session modes are stubbed
and rejected at construction so misconfiguration fails fast at startup.
"""

import logging
import re
import time

from core.parser import (
    CANCEL_WORDS,
    CONFIRM_WORDS,
    DEAFEN_WORD,
    INPUT_EXIT_PHRASES,
    INPUT_TRIGGER,
    LISTEN_WORD,
    input_command,
    normalize_transcript,
    parse_command,
)

logger = logging.getLogger(__name__)

IMPLEMENTED_MODES = ("vad_continuous", "push_to_talk")
STUBBED_MODES = ("wake_required", "wake_then_session", "adaptive_wake")

CONFIRM_TIMEOUT_SECONDS = 15

LOW_RISK = frozenset({
    "scroll_up", "scroll_down", "page_up", "page_down",
    "jump_top", "jump_bottom", "hints_show", "hints_hide", "links_show", "focus_page",
    "highlight_text", "highlight_next", "highlight_previous", "clear_highlights",
    "link_select",  # numbered-link select is visual only; the click stays MEDIUM
    "input_text",  # typing into a field the user already focused; no confirmation
    "cancel",
})
MEDIUM_RISK = frozenset({
    "nav_back", "nav_forward", "nav_reload",
    "tab_new", "tab_next", "tab_prev", "click", "open_new_tab", "focus_address",
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


def _payload_after(raw, word):
    """
    Everything after the first whole-word occurrence of `word` in the raw
    transcript, preserving the remainder's casing/punctuation. Used to recover a
    same-breath dictation payload ("input my name is Bob" -> "my name is Bob").
    Anything before the trigger (e.g. a leading wake word) is dropped with it.
    """
    match = re.search(r'\b' + re.escape(word) + r'\b', raw, flags=re.IGNORECASE)
    if not match:
        return ""
    return raw[match.end():].strip(" \t,.")


class ActivationPolicy:

    def __init__(self, listener_config, safety_config, voice_chat_config=None):
        self.mode = listener_config.get("mode", "vad_continuous")
        if self.mode in STUBBED_MODES:
            raise NotImplementedError(
                f"Listener mode '{self.mode}' is not implemented yet "
                f"(available: {', '.join(IMPLEMENTED_MODES)})"
            )
        if self.mode not in IMPLEMENTED_MODES:
            raise ValueError(f"Unknown listener mode: {self.mode}")

        self.wake_phrase = normalize_transcript(listener_config.get("wake_phrase", "arianna"))
        self.session_timeout = listener_config.get("session_timeout_seconds", 300)
        self.confirm_high = safety_config.get("confirm_high_risk_commands", True)
        self.allow_continuous = safety_config.get("allow_continuous_commands_without_wake", True)

        self.session_active_until = 0.0
        self.pending_command = None
        self.pending_until = 0.0

        # Voice toggling requires a wake phrase; set_deafened() works regardless.
        self.deafened = False
        self.deafen_phrase = f"{self.wake_phrase} {DEAFEN_WORD}" if self.wake_phrase else None
        self.listen_phrase = f"{self.wake_phrase} {LISTEN_WORD}" if self.wake_phrase else None

        # Input (dictation) mode. Driven here plus the listener's silence timer.
        self.input_silence_timeout = listener_config.get("input_silence_timeout_seconds", 5)
        self.in_input_mode = False
        self.input_deadline = 0.0

        # Voice chat: wake-gated free-form speech (vad_continuous only). Aliases
        # are accepted wake spellings — Whisper may not write "arianna".
        vc = voice_chat_config or {}
        self.chat_enabled = bool(vc.get("enabled", False))
        aliases = tuple(a for a in (normalize_transcript(x) for x in vc.get("wake_aliases", ()))
                        if a and a != self.wake_phrase)
        self.wake_words = ((self.wake_phrase,) if self.wake_phrase else ()) + aliases

    def _touch_session(self, now):
        self.session_active_until = now + self.session_timeout

    def _session_active(self, now):
        return now < self.session_active_until

    def _strip_wake_normalized(self, text):
        """Remainder after a leading wake spelling in normalized text, else None."""
        for wake in self.wake_words:
            if text.startswith(wake + " "):
                return text[len(wake) + 1:].strip()
        return None

    def _strip_wake_raw(self, raw):
        """Drop a leading wake token (any spelling/casing/punctuation) from the raw
        transcript, preserving the remainder verbatim."""
        for wake in self.wake_words:
            pattern = r'^\W*' + r'\W+'.join(re.escape(t) for t in wake.split()) + r'\b[\s,.!?:;-]*'
            match = re.match(pattern, raw, flags=re.IGNORECASE)
            if match:
                return raw[match.end():].strip()
        return raw.strip()

    @staticmethod
    def _has_real_words(text):
        """False when the text is only Vosk unknown-token residue ("unk unk")."""
        return any(t != "unk" for t in text.split())

    def exit_input_mode(self):
        """Leave input mode. Returns True if it was active (so the caller can log/notify)."""
        was_active = self.in_input_mode
        self.in_input_mode = False
        return was_active

    def refresh_input_activity(self, now):
        """Hold input mode open while the user is still speaking."""
        if self.in_input_mode:
            self.input_deadline = now + self.input_silence_timeout

    def input_expired(self, now):
        """True once input mode has been silent past the timeout."""
        return self.in_input_mode and now >= self.input_deadline

    def confirm_pending(self, now=None):
        """Name of the high-risk command awaiting a spoken 'confirm', or None when
        nothing is pending or the confirm window has already elapsed. Lets the
        listener drive an on-screen prompt without reaching into policy internals."""
        now = time.monotonic() if now is None else now
        if self.pending_command is not None and now < self.pending_until:
            return self.pending_command["name"]
        return None

    def clear_pending_confirm(self):
        """Drop any pending high-risk confirmation (e.g. when the mic is released).
        Returns True if one was pending."""
        was_pending = self.pending_command is not None
        self.pending_command = None
        return was_pending

    def set_deafened(self, deafened):
        """Enter/leave the deafened state (voice or extension initiated). Entering
        also ends dictation and drops a pending confirm, mirroring a mic release.
        Returns True if the state changed."""
        deafened = bool(deafened)
        if deafened == self.deafened:
            return False
        self.deafened = deafened
        if deafened:
            self.exit_input_mode()
            self.clear_pending_confirm()
        return True

    def evaluate(self, transcript, confidence=1.0, now=None, wake_heard=False):
        now = time.monotonic() if now is None else now
        text = normalize_transcript(transcript)
        if not text:
            return None, "empty"

        # Checked before input mode so the wake phrase works mid-dictation (tradeoff: these phrases can't be dictated).
        if self.deafen_phrase and text == self.deafen_phrase:
            self.set_deafened(True)
            return None, "deafen"
        if self.listen_phrase and text == self.listen_phrase:
            self._touch_session(now)
            if self.set_deafened(False):
                return None, "undeafen"
            return None, "already_listening"
        if self.deafened:
            return None, "deafened"

        # Expire a stale pending confirmation.
        if self.pending_command is not None and now >= self.pending_until:
            self.pending_command = None

        # Input mode: dictate everything verbatim until the user exits. Bypasses
        # wake-stripping and the parser so spoken command words ("scroll down")
        # are typed, not executed. The raw transcript keeps Whisper's casing.
        if self.in_input_mode:
            self.input_deadline = now + self.input_silence_timeout
            if text in INPUT_EXIT_PHRASES:
                self.in_input_mode = False
                return None, "input_end"
            self._touch_session(now)
            return input_command(transcript.strip(), confidence), "input"

        # Confirmation flow takes priority.
        if self.pending_command is not None:
            if text in CONFIRM_WORDS:
                command = self.pending_command
                self.pending_command = None
                self._touch_session(now)
                return command, "confirmed"
            if text in CANCEL_WORDS:
                self.pending_command = None
                return None, "cancelled"
            self.pending_command = None  # any other utterance cancels

        session_ok = self._session_active(now)
        wake_prefixed = False

        if self.mode == "push_to_talk":
            # Capture is gated externally; treat each utterance as in-session.
            session_ok = True
        else:  # vad_continuous
            if text in self.wake_words:
                self._touch_session(now)
                return None, "wake_only"
            stripped = self._strip_wake_normalized(text)
            if stripped is not None:
                text = stripped
                self._touch_session(now)
                session_ok = True
                wake_prefixed = True
            elif wake_heard:
                # Vosk confirmed the wake acoustically; the accurate transcript may
                # spell it unrecognizably. Same session semantics as a textual wake.
                self._touch_session(now)
                session_ok = True
                wake_prefixed = True
            elif self.allow_continuous:
                session_ok = True
            elif not session_ok:
                return None, "no_session"

        # Enter input mode on "input" (with an optional same-breath payload typed
        # right away). Subsequent utterances are handled by the in_input_mode
        # branch above until the user exits.
        if text == INPUT_TRIGGER or text.startswith(INPUT_TRIGGER + " "):
            self.in_input_mode = True
            self.input_deadline = now + self.input_silence_timeout
            self._touch_session(now)
            payload = _payload_after(transcript, INPUT_TRIGGER)
            if payload:
                return input_command(payload, confidence), "input_start"
            return None, "input_start"

        command = parse_command(text, confidence)
        if command is None:
            # Wake-gated chat: the payload comes from the raw transcript so the LLM
            # sees Whisper's casing/punctuation, not the parser normalization.
            if self.chat_enabled and wake_prefixed and self._has_real_words(text):
                payload = self._strip_wake_raw(transcript)
                return ({
                    "type": "command",
                    "name": "voice_chat",
                    "args": {"text": payload},
                    "meta": {"confidence": confidence, "raw": transcript,
                             "wake_heard": wake_heard},
                }, "chat")
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
