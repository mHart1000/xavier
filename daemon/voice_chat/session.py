"""
Voice-chat session: one thread per chat turn, orchestrating
pause mic -> stream AIUI reply into playback -> resume mic.

Listener.pause() joins the worker thread, so it must never run on the worker
itself: handle() (called from the worker) only spawns the session thread and
returns. Events go through emit_event, which is cross-thread safe (main.py's
safe_send holds a lock).
"""

import logging
import threading
import time

from audio.output import AudioOutput
from voice_chat.client import VoiceChatClient, VoiceChatError, read_chunk

logger = logging.getLogger(__name__)


class VoiceChatSession:

    def __init__(self, config, listener, emit_event):
        self.config = config.get("voice_chat", {})
        self.listener = listener
        self.emit_event = emit_event
        self.client = None            # lazy; token + conversation persist across turns
        self.conversation_id = None
        self._lock = threading.Lock()
        self._active = False
        if self.config.get("enabled") and not self._has_credentials():
            logger.warning("voice_chat enabled but credentials missing; set "
                           "XAVIER_AIUI_EMAIL / XAVIER_AIUI_PASSWORD (daemon/.env)")

    def _has_credentials(self):
        return bool(self.config.get("email") and self.config.get("password"))

    def handle(self, text):
        """Start a chat turn. Called from the listener worker thread; returns
        immediately. Drops the utterance if a chat is already in progress."""
        with self._lock:
            if self._active:
                logger.info("voice chat busy; dropping utterance %r", text)
                return
            self._active = True
        threading.Thread(target=self._run, args=(text,), daemon=True,
                         name="voice-chat").start()

    def _ensure_client(self):
        if self.client is None:
            if not self._has_credentials():
                raise VoiceChatError("voice_chat credentials not configured "
                                     "(XAVIER_AIUI_EMAIL / XAVIER_AIUI_PASSWORD)")
            self.client = VoiceChatClient(self.config)
        return self.client

    def _run(self, text):
        error = None
        timed_out = False
        output = None
        try:
            self.emit_event({"type": "voice_chat", "state": "start"})
            self.listener.pause()                    # safe: not the worker thread
            client = self._ensure_client()
            resp, rate, channels, conv_id = client.chat(text, self.conversation_id)
            if conv_id:
                self.conversation_id = conv_id       # failed turns keep the old one
            output = AudioOutput(rate, channels,
                                 command=self.config.get("playback_command"))
            output.start()
            deadline = time.monotonic() + self.config.get("max_response_seconds", 120)
            while True:
                if time.monotonic() >= deadline:
                    timed_out = True
                    logger.warning("voice chat reply hit max_response_seconds; "
                                   "aborting playback")
                    break
                chunk = read_chunk(resp, 4096)
                if not chunk:
                    break
                output.write(chunk)
        except VoiceChatError as e:
            error = str(e)
            logger.error("voice chat failed: %s", e)
        except Exception as e:
            error = str(e)
            logger.exception("voice chat failed")
        finally:
            if output is not None:
                try:
                    if error or timed_out:
                        output.abort()               # drop buffered audio
                    else:
                        output.close()               # drain the speech tail
                except Exception:
                    logger.exception("playback teardown failed")
            if self.client is not None:
                self.client.close()
            try:
                self.listener.resume()               # before the end event (badge order)
            except Exception:
                logger.exception("listener resume failed after voice chat")
            event = {"type": "voice_chat", "state": "error" if error else "end"}
            if error:
                event["error"] = error
            self.emit_event(event)
            with self._lock:
                self._active = False
