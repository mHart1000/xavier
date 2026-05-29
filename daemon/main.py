#!/usr/bin/env python3
"""
Xavier Voice Browser Daemon — entry point.

Runs as a Firefox Native Messaging host: blocks on stdin reading length-prefixed
JSON messages from the extension and emits commands on stdout. Stays alive for
the lifetime of the Firefox-extension port; exits on EOF.

When the extension sends `ready`, the speech Listener starts: microphone -> VAD
-> segmenter -> STT -> activation policy -> parser -> command. Run with
`--mic-test` to drive the same pipeline without Firefox (commands print to
stderr) for local debugging.
"""

import json
import logging
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import load_config
from core.listener import Listener
from native_messaging.framing import read_message, send_message

# stdout is shared by the main loop (ping replies) and the listener thread.
_send_lock = threading.Lock()
_listener = None
_listener_started = False


def setup_logging(level="INFO", log_file=None):
    # stderr is invisible when Firefox (esp. Snap) launches the daemon, so also
    # log to a file the user can tail during e2e testing.
    handlers = [logging.StreamHandler(sys.stderr)]
    if log_file:
        try:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_file, mode="a"))
        except OSError as e:
            print(f"Could not open log file {log_file}: {e}", file=sys.stderr)
    logging.basicConfig(
        level=getattr(logging, str(level).upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
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


def handle_ready(message, logger):
    global _listener_started
    logger.info("Extension ready: %s", message.get("meta", {}))
    if _listener_started:
        return
    try:
        _listener.start()
        _listener_started = True
    except Exception:
        logger.exception("Failed to start speech listener; daemon stays up without STT")


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
    global _listener
    config = load_config()
    setup_logging(config["logging"]["level"], config["logging"].get("file"))
    logger = logging.getLogger(__name__)
    logger.info("Xavier daemon started; waiting for extension messages on stdin")

    _listener = Listener(config, emit_command)

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
    finally:
        if _listener_started:
            _listener.stop()


def run_mic_test():
    """Drive the Listener without Native Messaging; print commands to stderr."""
    config = load_config()
    setup_logging("DEBUG", config["logging"].get("file"))  # always verbose in mic-test
    logger = logging.getLogger(__name__)
    logger.info("Mic test mode — speak commands; Ctrl-C to exit")

    def emit_stderr(command):
        command["id"] = str(uuid.uuid4())
        print(json.dumps(command), file=sys.stderr, flush=True)
        return True

    listener = Listener(config, emit_stderr)
    listener.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Stopping mic test")
    finally:
        listener.stop()


if __name__ == "__main__":
    if "--list-devices" in sys.argv:
        import subprocess
        try:
            subprocess.run(["pactl", "list", "sources", "short"], check=False)
        except FileNotFoundError:
            print("pactl not found; install pulseaudio-utils to list sources.",
                  file=sys.stderr)
    elif "--mic-test" in sys.argv:
        run_mic_test()
    else:
        main()
