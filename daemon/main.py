#!/usr/bin/env python3
"""
Xavier Voice Browser Daemon — entry point.

Runs as a Firefox Native Messaging host: blocks on stdin reading length-prefixed
JSON messages from the extension and emits commands on stdout. Stays alive for
the lifetime of the Firefox-extension port; exits on EOF.

Phase 4 verification: once the extension sends `ready`, a background thread emits
a repeating bounce of scroll commands so the daemon->extension->page path can be
observed end-to-end. All of this (PHASE4_* + start_test_emitter) is removed in
Phase 6 when STT/push-to-talk drives command emission.
"""

import sys
import logging
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from native_messaging.framing import read_message, send_message
from core.parser import parse_command


# --- Phase 4 test scaffold (remove in Phase 6) -----------------------------
PHASE4_TEST_SEQUENCE = [
    "scroll down", "scroll down", "scroll down",
    "scroll up", "scroll up", "scroll up",
]
PHASE4_TEST_INTERVAL_SECONDS = 3
# ---------------------------------------------------------------------------

# stdout is shared by the main loop (ping replies) and the emitter thread.
_send_lock = threading.Lock()
_emitter_started = False


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


def safe_send(message):
    """Send under a lock. Returns False if the pipe is closed (extension gone)."""
    with _send_lock:
        try:
            send_message(message)
            return True
        except (BrokenPipeError, OSError):
            return False


def emit_command(command):
    command["id"] = str(uuid.uuid4())
    return safe_send(command)


def reply_ack(msg_id):
    safe_send({"type": "ack", "id": msg_id, "meta": {"ok": True}})


def start_test_emitter(logger):
    """Phase 4 scaffold: emit the bounce sequence on a timer until the pipe closes."""
    global _emitter_started
    if _emitter_started:
        return
    _emitter_started = True

    def loop():
        i = 0
        while True:
            time.sleep(PHASE4_TEST_INTERVAL_SECONDS)
            transcript = PHASE4_TEST_SEQUENCE[i % len(PHASE4_TEST_SEQUENCE)]
            i += 1

            command = parse_command(transcript)
            if command is None:
                logger.error("Test transcript did not parse: %r", transcript)
                continue

            if not emit_command(command):
                logger.info("Pipe closed; stopping test emitter")
                return
            logger.info("Sent test command: %s", command["name"])

    threading.Thread(target=loop, daemon=True).start()
    logger.info("Phase 4 test emitter started (%ss interval)", PHASE4_TEST_INTERVAL_SECONDS)


def handle_ready(message, logger):
    logger.info("Extension ready: %s", message.get("meta", {}))
    start_test_emitter(logger)


def handle_ack(message, logger):
    logger.info("ack id=%s", message.get("id"))


def handle_error(message, logger):
    meta = message.get("meta") or {}
    logger.warning(
        "error id=%s code=%s message=%s",
        message.get("id"),
        meta.get("code"),
        meta.get("message"),
    )


def handle_ping(message, logger):
    msg_id = message.get("id")
    logger.debug("ping id=%s", msg_id)
    reply_ack(msg_id)


HANDLERS = {
    "ready": handle_ready,
    "ack": handle_ack,
    "error": handle_error,
    "ping": handle_ping,
}


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Xavier daemon started; waiting for extension messages on stdin")

    try:
        while True:
            message = read_message()
            if message is None:
                logger.info("stdin closed; daemon exiting")
                break

            msg_type = message.get("type")
            handler = HANDLERS.get(msg_type)
            if handler is None:
                logger.warning("Unknown message type: %r", msg_type)
                continue

            handler(message, logger)
    except KeyboardInterrupt:
        logger.info("Interrupted; daemon exiting")
    except Exception:
        logger.exception("Fatal error in daemon loop")
        sys.exit(1)


if __name__ == "__main__":
    main()
