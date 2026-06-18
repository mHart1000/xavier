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

# Words that confirm a HIGH_RISK command; must be in command_grammar() (see activation_policy).
CONFIRM_WORDS = ("confirm", "confirmed")

# Words that abort a pending confirmation (see activation_policy).
CANCEL_WORDS = ("cancel",)

# Leading position words: "highlight <ordinal> <target>" (1-based).
ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}

# Trailing position words: "highlight expand three" == "highlight third expand".
CARDINAL_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# Trailing-position homonyms for numbers Whisper mis-hears ("two" -> "to").
NUMBER_HOMONYMS = {
    "won": 1, "to": 2, "too": 2, "for": 4, "fore": 4, "ate": 8,
}


def command_hotwords():
    """Distinct words across the command vocabulary, for biasing the recognizer."""
    words = {"highlight"}  # highlight_text is trigger-routed, not a PHRASE_COMMANDS entry
    words.update(ORDINAL_WORDS)   # bias "highlight <ordinal> <target>"
    words.update(CARDINAL_WORDS)  # bias "highlight <target> <number>"
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
        inner = highlight_match.group(1).strip()
        ordinal, text, source = _split_position(inner)
        args = {"text": text}
        if ordinal is not None:
            args["ordinal"] = ordinal
            if source == "trail":
                # Keep the full phrase: the trailing number may have been a real word.
                args["literal"] = inner
        return _make_command("highlight_text", args, confidence, raw)

    url_match = re.match(r'^open url (.+)$', normalized)
    if url_match:
        url = _spoken_to_url(url_match.group(1))
        return _make_command("open_url", {"url": url}, confidence, raw)

    logger.warning(f"No command matched for transcript: {raw}")
    return None


def _numeric_token(token):
    """Token -> int for a bare digit, optionally with an ordinal suffix (3, 3rd)."""
    match = re.match(r'^(\d+)(?:st|nd|rd|th)?$', token)
    return int(match.group(1)) if match else None


def _split_position(text):
    """
    Pull a 1-based position out of a highlight phrase, returning
    (pos_or_None, rest, source) where source is "lead", "trail", or None:
      - leading ordinal: "third expand" / "3 expand"            -> "lead"
      - trailing number: "expand three" / "expand 3" / "expand to" -> "trail"
    A target must remain on the other side, so "highlight first" / "highlight
    three" stay literal. Cardinals and homonyms are read only as a trailing
    position, not a leading one, so a target like "one piece" is left intact.
    """
    tokens = text.split()
    if len(tokens) < 2:
        return None, text, None

    head = tokens[0]
    lead = ORDINAL_WORDS.get(head)
    if lead is None:
        lead = _numeric_token(head)
    if lead is not None:
        return lead, " ".join(tokens[1:]), "lead"

    tail_token = tokens[-1]
    tail = (ORDINAL_WORDS.get(tail_token)
            or CARDINAL_WORDS.get(tail_token)
            or NUMBER_HOMONYMS.get(tail_token))
    if tail is None:
        tail = _numeric_token(tail_token)
    if tail is not None:
        return tail, " ".join(tokens[:-1]), "trail"

    return None, text, None


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
