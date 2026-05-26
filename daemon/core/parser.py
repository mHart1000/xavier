"""
Command parser - converts normalized transcripts into structured commands.

Output command names match protocol/protocol.md v1.0.
"""

import re
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
    # TODO(phase 7): gate tab_close behind a confirmation phrase per protocol Safety §.
    "close tab": "tab_close",
    "next tab": "tab_next",
    "previous tab": "tab_prev",
    "prev tab": "tab_prev",
    "show hints": "hints_show",
    "hints": "hints_show",
    "hide hints": "hints_hide",
    "focus address": "focus_address",
    "address bar": "focus_address",
    "focus page": "focus_page",
    "focus body": "focus_page",
}


def command_hotwords():
    """Distinct words across the command vocabulary, for biasing the recognizer."""
    words = {"click"}  # hint_click prefix isn't in PHRASE_COMMANDS
    for phrase in PHRASE_COMMANDS:
        words.update(phrase.split())
    return " ".join(sorted(words))


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

    logger.warning(f"No command matched for transcript: {raw}")
    return None


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
