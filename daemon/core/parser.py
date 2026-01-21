"""
Command parser - converts normalized transcripts into structured commands.
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
    Parse a normalized transcript into a command object.
    Returns a dict matching the protocol schema or None if no match.
    
    Returns:
    {
      "type": "command",
      "id": <will be added by caller>,
      "name": "command_name",
      "args": {...},
      "meta": {
        "confidence": float,
        "raw": original_transcript
      }
    }
    """
    normalized = normalize_transcript(transcript)
    raw = transcript
    
    # Navigation commands
    if normalized in ["back", "go back"]:
        return _make_command("back", {}, confidence, raw)
    
    if normalized in ["forward", "go forward"]:
        return _make_command("forward", {}, confidence, raw)
    
    if normalized in ["reload", "refresh"]:
        return _make_command("reload", {}, confidence, raw)
    
    # Scrolling commands
    if normalized in ["scroll up", "up"]:
        return _make_command("scroll_up", {}, confidence, raw)
    
    if normalized in ["scroll down", "down"]:
        return _make_command("scroll_down", {}, confidence, raw)
    
    if normalized in ["page up"]:
        return _make_command("page_up", {}, confidence, raw)
    
    if normalized in ["page down"]:
        return _make_command("page_down", {}, confidence, raw)
    
    # Jump commands
    if normalized in ["jump top", "top"]:
        return _make_command("jump_top", {}, confidence, raw)
    
    if normalized in ["jump bottom", "bottom"]:
        return _make_command("jump_bottom", {}, confidence, raw)
    
    # Tab commands
    if normalized in ["new tab", "open tab"]:
        return _make_command("new_tab", {}, confidence, raw)
    
    if normalized in ["close tab"]:
        return _make_command("close_tab", {}, confidence, raw)
    
    if normalized in ["next tab"]:
        return _make_command("next_tab", {}, confidence, raw)
    
    if normalized in ["previous tab", "prev tab"]:
        return _make_command("previous_tab", {}, confidence, raw)
    
    # Hint commands
    if normalized in ["show hints", "hints"]:
        return _make_command("show_hints", {}, confidence, raw)
    
    if normalized in ["hide hints"]:
        return _make_command("hide_hints", {}, confidence, raw)
    
    # Hint click parsing: "click AF", "click a f", etc.
    hint_match = re.match(r'^click\s+([a-z\s]+)$', normalized)
    if hint_match:
        hint_code = hint_match.group(1).replace(' ', '').upper()
        return _make_command("hint_click", {"hint": hint_code}, confidence, raw)
    
    # Focus commands (optional MVP)
    if normalized in ["focus address", "address bar"]:
        return _make_command("focus_address", {}, confidence, raw)
    
    logger.warning(f"No command matched for transcript: {raw}")
    return None


def _make_command(name, args, confidence, raw):
    """Helper to construct a command dict without the id field."""
    return {
        "type": "command",
        "name": name,
        "args": args,
        "meta": {
            "confidence": confidence,
            "raw": raw
        }
    }
