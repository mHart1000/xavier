"""
Command parser - converts normalized transcripts into structured commands.

Output command names match protocol/protocol.md v1.0.
"""

import re
import string
import logging

logger = logging.getLogger(__name__)


def normalize_transcript(transcript):
    """
    Normalize a transcript for parsing:
    - lowercase
    - remove punctuation
    - collapse whitespace
    """
    transcript = transcript.lower()
    transcript = re.sub(r'[^\w\s]', '', transcript)
    transcript = re.sub(r'\s+', ' ', transcript)
    return transcript.strip()


# Canonical vocabulary: normalized spoken phrase -> command name. Single source
# of truth for both matching and recognizer biasing (see command_hotwords()).
# hint_click is handled separately because it carries a variable code argument.
PHRASE_COMMANDS = {
    "back": "nav_back",
    "go back": "nav_back",
    "forward": "nav_forward",
    "go forward": "nav_forward",
    "reload": "nav_reload",
    "refresh": "nav_reload",
    "scroll up": "scroll_up",
    "up": "scroll_up",
    "scroll down": "scroll_down",
    "down": "scroll_down",
    "page up": "page_up",
    "page down": "page_down",
    "jump top": "jump_top",
    "top": "jump_top",
    "jump bottom": "jump_bottom",
    "bottom": "jump_bottom",
    "new tab": "tab_new",
    "open tab": "tab_new",
    # tab_close is gated as HIGH_RISK (spoken confirm) in activation_policy.
    "close tab": "tab_close",
    "next tab": "tab_next",
    "previous tab": "tab_prev",
    "prev tab": "tab_prev",
    "show hints": "hints_show",
    "hints": "hints_show",
    "hide hints": "hints_hide",
    "click": "click",
    "open in new tab": "open_new_tab",
    "open in a new tab": "open_new_tab",
    "control click": "open_new_tab",
    "clear highlight": "clear_highlights",
    "clear highlights": "clear_highlights",
    "cancel": "cancel",
    "next": "highlight_next",
    "previous": "highlight_previous",
    "focus address": "focus_address",
    "address bar": "focus_address",
    "focus page": "focus_page",
    "focus body": "focus_page",
}

# Spoken words that confirm a HIGH_RISK command (see activation_policy). These
# must be in command_grammar() or the Vosk fast path maps them to "[unk]".
CONFIRM_WORDS = ("confirm", "confirmed")

# Spoken words that abort a pending confirmation (see activation_policy). "cancel"
# is multipurpose: with no pending command it parses to the cancel command and
# dismisses transient page state in the extension instead.
CANCEL_WORDS = ("cancel",)

# Leading ordinal in "highlight <ordinal> <target>" (e.g. "highlight third expand")
# selects which match to start on. 1-based; the extension clamps out-of-range.
ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}


def command_hotwords():
    """Distinct words across the command vocabulary, for biasing the recognizer."""
    words = {"highlight"}  # highlight_text is trigger-routed, not a PHRASE_COMMANDS entry
    words.update(ORDINAL_WORDS)  # bias "highlight <ordinal> <target>"
    for phrase in PHRASE_COMMANDS:
        words.update(phrase.split())
    return " ".join(sorted(words))


def command_grammar(wake_phrase=None):
    """
    Vosk grammar (list of allowable tokens) that constrains recognition to the
    command vocabulary. Restricting to known words makes Vosk both faster and
    more accurate. "[unk]" lets out-of-grammar audio map to an unknown token so
    random speech is rejected rather than forced onto a command word.
    """
    words = {"click", "open", "url", "highlight"}  # open/url/highlight route to Whisper
    words.update(CONFIRM_WORDS)       # gate the HIGH_RISK confirmation step
    words.update(CANCEL_WORDS)        # abort a pending confirmation
    for phrase in PHRASE_COMMANDS:
        words.update(phrase.split())
    words.update(string.ascii_lowercase)  # single-letter hint codes (a-z)
    if wake_phrase:
        words.update(normalize_transcript(wake_phrase).split())
    return sorted(words) + ["[unk]"]


def command_triggers():
    """Normalized phrases that route an utterance to the Whisper (accuracy) path."""
    return ("open url", "highlight")


def parse_command(transcript, confidence=1.0):
    """
    Parse a transcript into a protocol command dict.
    Returns None if no command matches.

    Returned shape (caller assigns id):
    {
      "type": "command",
      "name": "<canonical>",
      "args": {...},
      "meta": {"confidence": float, "raw": str}
    }
    """
    normalized = normalize_transcript(transcript)
    raw = transcript

    name = PHRASE_COMMANDS.get(normalized)
    if name is not None:
        return _make_command(name, {}, confidence, raw)

    hint_match = re.match(r'^click\s+([a-z\s]+)$', normalized)
    if hint_match:
        code = hint_match.group(1).replace(' ', '').upper()
        return _make_command("hint_click", {"code": code}, confidence, raw)

    highlight_match = re.match(r'^highlight (.+)$', normalized)
    if highlight_match:
        ordinal, text = _split_ordinal(highlight_match.group(1).strip())
        args = {"text": text}
        if ordinal is not None:
            args["ordinal"] = ordinal
        return _make_command("highlight_text", args, confidence, raw)

    url_match = re.match(r'^open url (.+)$', normalized)
    if url_match:
        url = _spoken_to_url(url_match.group(1))
        return _make_command("open_url", {"url": url}, confidence, raw)

    logger.warning(f"No command matched for transcript: {raw}")
    return None


def _split_ordinal(text):
    """
    Split a leading ordinal off a highlight phrase: an ordinal word (first..tenth)
    or a numeric form (3, 3rd). Returns (ordinal_or_None, rest). Only treats the
    head as an ordinal when a target follows, so "highlight first" stays a literal
    "first" match.
    """
    tokens = text.split()
    if len(tokens) < 2:
        return None, text
    head, rest = tokens[0], " ".join(tokens[1:])
    if head in ORDINAL_WORDS:
        return ORDINAL_WORDS[head], rest
    digit = re.match(r'^(\d+)(?:st|nd|rd|th)?$', head)
    if digit:
        return int(digit.group(1)), rest
    return None, text


def _spoken_to_url(spoken):
    """
    Turn a basic spoken URL into a real one. Input is already normalized
    (lowercase, punctuation stripped), so spoken "dot"/"slash" are restored to
    "." / "/", remaining spaces are dropped, and https:// is prepended when no
    scheme is present. Best-effort only — see the open_url note in the plan.
    """
    url = spoken.replace(" dot ", ".").replace(" slash ", "/")
    url = url.replace(" ", "")
    if "://" not in url:
        url = "https://" + url
    return url


def _make_command(name, args, confidence, raw):
    return {
        "type": "command",
        "name": name,
        "args": args,
        "meta": {
            "confidence": confidence,
            "raw": raw
        }
    }
