"""
Native Messaging protocol framing for Firefox.
Handles the 4-byte length prefix + JSON payload format.
"""

import sys
import struct
import json
import logging

logger = logging.getLogger(__name__)


def read_message():
    """
    Read a message from stdin using Firefox Native Messaging format.
    Returns the parsed JSON object or None if EOF/error.
    """
    try:
        raw_length = sys.stdin.buffer.read(4)
        if not raw_length or len(raw_length) != 4:
            logger.debug("EOF or incomplete length header")
            return None
        
        message_length = struct.unpack('=I', raw_length)[0]
        
        if message_length == 0:
            logger.warning("Received zero-length message")
            return None
        
        raw_message = sys.stdin.buffer.read(message_length)
        if len(raw_message) != message_length:
            logger.error(f"Expected {message_length} bytes, got {len(raw_message)}")
            return None
        
        message = json.loads(raw_message.decode('utf-8'))
        logger.debug(f"Received message: {message}")
        return message
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"Error reading message: {e}")
        return None


def send_message(message):
    """
    Send a message to stdout using Firefox Native Messaging format.
    Message should be a dict that will be JSON-encoded.
    """
    try:
        encoded_content = json.dumps(message).encode('utf-8')
        encoded_length = struct.pack('=I', len(encoded_content))
        
        sys.stdout.buffer.write(encoded_length)
        sys.stdout.buffer.write(encoded_content)
        sys.stdout.buffer.flush()
        
        logger.debug(f"Sent message: {message}")
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise
