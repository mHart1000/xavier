#!/usr/bin/env python3
"""
Xavier Voice Browser Daemon
Main entry point 

For MVP: Push-to-talk mode with Enter key
"""

import sys
import logging
import json
import uuid
import time
from pathlib import Path

# Add daemon directory to path
sys.path.insert(0, str(Path(__file__).parent))

from native_messaging.framing import read_message, send_message
from core.parser import parse_command


def setup_logging():
    """Configure logging to stderr (stdin/stdout reserved for native messaging)."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )


def send_command(command_dict):
    """Send a command to the extension with a unique ID."""
    command_dict["id"] = str(uuid.uuid4())
    send_message(command_dict)


def send_ack(command_id, success=True, message=""):
    """Send an acknowledgment message."""
    ack = {
        "type": "ack",
        "id": command_id,
        "ok": success,
        "message": message
    }
    send_message(ack)


def send_error(command_id, error_message):
    """Send an error message."""
    error = {
        "type": "error",
        "id": command_id,
        "message": error_message
    }
    send_message(error)


def main():
    """Main daemon loop."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Xavier Voice Browser Daemon starting...")
    logger.info("Native messaging interface active")
    logger.info("MVP mode: Push-to-talk with Enter key (simulated for now)")
    
    # Send ready signal
    send_message({
        "type": "ready",
        "id": str(uuid.uuid4()),
        "message": "Daemon ready"
    })
    
    logger.info("READY - Press Enter to simulate voice command (hardcoded for Phase 3)")
    
    # test loop with hardcoded command instead of stt
    try:
        while True:
            # Wait for Enter key on stderr (not stdin - that's for native messaging)
            # For now, we'll simulate this with a simple timer
            logger.info("Simulating voice command in 5 seconds...")
            time.sleep(5)
            
            # Hardcoded test command
            test_transcript = "scroll down"
            logger.info(f"Simulated transcript: {test_transcript}")
            
            # Parse command
            command = parse_command(test_transcript)
            
            if command:
                logger.info(f"Parsed command: {command['name']}")
                send_command(command)
            else:
                logger.warning(f"Could not parse transcript: {test_transcript}")
                send_error(str(uuid.uuid4()), f"Unknown command: {test_transcript}")
            
            # For testing purposes, send one command then exit
            logger.info("Test command sent. Exiting...")
            break
            
    except KeyboardInterrupt:
        logger.info("Daemon shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
