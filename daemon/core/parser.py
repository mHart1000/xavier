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

    if normalized in ("back", "go back"):
        return _make_command("nav_back", {}, confidence, raw)

    if normalized in ("forward", "go forward"):
        return _make_command("nav_forward", {}, confidence, raw)

    if normalized in ("reload", "refresh"):
        return _make_command("nav_reload", {}, confidence, raw)

    if normalized in ("scroll up", "up"):
        return _make_command("scroll_up", {}, confidence, raw)

    if normalized in ("scroll down", "down"):
        return _make_command("scroll_down", {}, confidence, raw)

    if normalized == "page up":
        return _make_command("page_up", {}, confidence, raw)

    if normalized == "page down":
        return _make_command("page_down", {}, confidence, raw)

    if normalized in ("jump top", "top"):
        return _make_command("jump_top", {}, confidence, raw)

    if normalized in ("jump bottom", "bottom"):
        return _make_command("jump_bottom", {}, confidence, raw)

    if normalized in ("new tab", "open tab"):
        return _make_command("tab_new", {}, confidence, raw)

    # TODO(phase 7): gate tab_close behind a confirmation phrase per protocol Safety §.
    if normalized == "close tab":
        return _make_command("tab_close", {}, confidence, raw)

    if normalized == "next tab":
        return _make_command("tab_next", {}, confidence, raw)

    if normalized in ("previous tab", "prev tab"):
        return _make_command("tab_prev", {}, confidence, raw)

    if normalized in ("show hints", "hints"):
        return _make_command("hints_show", {}, confidence, raw)

    if normalized == "hide hints":
        return _make_command("hints_hide", {}, confidence, raw)

    hint_match = re.match(r'^click\s+([a-z\s]+)$', normalized)
    if hint_match:
        code = hint_match.group(1).replace(' ', '').upper()
        return _make_command("hint_click", {"code": code}, confidence, raw)

    if normalized in ("focus address", "address bar"):
        return _make_command("focus_address", {}, confidence, raw)

    if normalized in ("focus page", "focus body"):
        return _make_command("focus_page", {}, confidence, raw)

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
