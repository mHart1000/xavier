"""
Streaming HTTP client for AIUI's voice-chat endpoint (stdlib only).

POST /api/voice_chat returns chunked audio/wav: a 44-byte header (its size
fields are bogus for a stream — ignored) followed by continuous s16le PCM.
The caller reads the response body incrementally and calls close() when done.
Auth is a bearer JWT from POST /api/login, cached in memory; an expired token
(401) triggers exactly one re-login + retry.
"""

import json
import logging
import struct
from http.client import HTTPConnection, HTTPException
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


class VoiceChatError(Exception):
    """Voice-chat request failure (connection, auth, protocol)."""


def _extract_token(header_value):
    """JWT from the login response's Authorization header ("Bearer <jwt>" or bare)."""
    value = (header_value or "").strip()
    if value.lower().startswith("bearer"):
        value = value[len("bearer"):].strip()
    if not value:
        raise VoiceChatError("login response had no usable Authorization header")
    return value


def _read_exact(resp, n):
    """Read exactly n bytes from a response (read() may return short)."""
    data = b""
    while len(data) < n:
        chunk = resp.read(n - len(data))
        if not chunk:
            raise VoiceChatError(f"response ended after {len(data)} bytes (wanted {n})")
        data += chunk
    return data


def _parse_wav_header(header):
    """(sample_rate, channels) from a 44-byte WAV header."""
    channels = struct.unpack_from("<H", header, 22)[0]
    sample_rate = struct.unpack_from("<I", header, 24)[0]
    if not (1 <= channels <= 8 and 8000 <= sample_rate <= 192000):
        raise VoiceChatError(
            f"implausible WAV header (rate={sample_rate}, channels={channels})")
    return sample_rate, channels


class VoiceChatClient:

    def __init__(self, vc_config):
        split = urlsplit(vc_config.get("base_url") or "http://localhost:3000")
        if split.scheme != "http":
            raise VoiceChatError(
                f"voice_chat.base_url must be http:// (got {split.scheme!r})")
        self.host = split.hostname
        self.port = split.port or 80
        self.prefix = split.path.rstrip("/")
        self.email = vc_config.get("email")
        self.password = vc_config.get("password")
        self.voice = vc_config.get("voice")
        self.speed = vc_config.get("speed")
        self.model_code = vc_config.get("model_code")
        self.connect_timeout = vc_config.get("connect_timeout_seconds", 5)
        self.read_timeout = vc_config.get("read_timeout_seconds", 30)
        self.token = None
        self._conn = None   # connection carrying the active streaming response

    def _request(self, method, path, body, headers):
        conn = HTTPConnection(self.host, self.port, timeout=self.connect_timeout)
        try:
            conn.request(method, self.prefix + path, body=body, headers=headers)
            conn.sock.settimeout(self.read_timeout)  # header wait + body reads
            return conn, conn.getresponse()
        except (HTTPException, OSError) as e:
            conn.close()
            raise VoiceChatError(f"AIUI request failed ({method} {path}): {e}") from e

    def login(self):
        body = json.dumps({"user": {"email": self.email, "password": self.password}})
        conn, resp = self._request("POST", "/api/login", body,
                                   {"Content-Type": "application/json"})
        try:
            if resp.status != 200:
                raise VoiceChatError(f"login failed: HTTP {resp.status}")
            self.token = _extract_token(resp.getheader("Authorization"))
            logger.info("voice chat: logged in to AIUI")
        finally:
            conn.close()

    def chat(self, text, conversation_id=None):
        """POST /api/voice_chat; returns (resp, sample_rate, channels, conversation_id).
        The caller streams resp.read() and must call close() when done."""
        payload = {"text": text}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if self.voice:
            payload["voice"] = self.voice
        if self.speed is not None:
            payload["speed"] = self.speed
        if self.model_code:
            payload["model_code"] = self.model_code
        body = json.dumps(payload)

        for retry in (False, True):
            if self.token is None:
                self.login()
            conn, resp = self._request("POST", "/api/voice_chat", body, {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            })
            if resp.status == 401 and not retry:
                logger.info("voice chat: token expired; re-logging in")
                self.token = None
                conn.close()
                continue
            if resp.status != 200:
                try:
                    detail = resp.read(500)
                except OSError:
                    detail = b""
                conn.close()
                raise VoiceChatError(f"voice_chat failed: HTTP {resp.status} {detail!r}")
            self._conn = conn
            try:
                sample_rate, channels = _parse_wav_header(_read_exact(resp, 44))
            except VoiceChatError:
                self.close()
                raise
            except OSError as e:
                self.close()
                raise VoiceChatError(f"reading WAV header failed: {e}") from e
            return resp, sample_rate, channels, resp.getheader("X-Conversation-Id")

    def close(self):
        """Tear down the streaming connection (idempotent); unblocks a stalled read."""
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
