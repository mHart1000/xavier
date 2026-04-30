#!/usr/bin/env python3
"""
Xavier Voice Browser Daemon — entry point.

Runs as a Firefox Native Messaging host: blocks on stdin reading length-prefixed
JSON messages from the extension and emits commands on stdout. Stays alive for
the lifetime of the Firefox-extension port; exits on EOF.

Phase 4 verification: when the extension sends `ready`, the daemon emits one
hardcoded test command so the handshake can be observed end-to-end. This is
removed in Phase 6 when STT-driven command emission lands.
"""

import sys
import logging
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from native_messaging.framing import read_message, send_message
from core.parser import parse_command


# TODO(phase 6): replace with STT-driven emission. Until then, this transcript
# is parsed and sent once on `ready` so Phase 4 handshake can be verified.
PHASE4_TEST_TRANSCRIPT = "scroll down"


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


def emit_command(command):
    command["id"] = str(uuid.uuid4())
    send_message(command)


def reply_ack(msg_id):
    send_message({"type": "ack", "id": msg_id, "meta": {"ok": True}})


def handle_ready(message, logger):
    logger.info("Extension ready: %s", message.get("meta", {}))

    command = parse_command(PHASE4_TEST_TRANSCRIPT)
    if command is None:
        logger.error("Phase 4 test transcript did not parse: %r", PHASE4_TEST_TRANSCRIPT)
        return

    emit_command(command)
    logger.info("Sent Phase 4 test command: %s", command["name"])


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
