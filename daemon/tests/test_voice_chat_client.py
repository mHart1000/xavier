"""Voice-chat HTTP client: token/WAV parsing and the login/401-retry flow."""

import struct
from unittest.mock import MagicMock, patch

import pytest

from voice_chat.client import (
    VoiceChatClient,
    VoiceChatError,
    _extract_token,
    _parse_wav_header,
    _read_exact,
    read_chunk,
)


def wav_header(rate=24000, channels=1):
    header = bytearray(44)
    header[0:4] = b"RIFF"
    struct.pack_into("<H", header, 22, channels)
    struct.pack_into("<I", header, 24, rate)
    return bytes(header)


def test_extract_token_strips_bearer():
    assert _extract_token("Bearer abc.def") == "abc.def"


def test_extract_token_accepts_bare():
    assert _extract_token("abc.def") == "abc.def"


def test_extract_token_missing_raises():
    for header in (None, "", "Bearer ", "Bearer"):
        with pytest.raises(VoiceChatError):
            _extract_token(header)


class DribbleResp:
    """read(n) that returns at most `step` bytes per call."""

    def __init__(self, data, step=10):
        self.data = data
        self.step = step

    def read(self, n):
        n = min(n, self.step)
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk


def test_read_exact_collects_short_reads():
    assert _read_exact(DribbleResp(b"x" * 44), 44) == b"x" * 44


def test_read_exact_premature_eof_raises():
    with pytest.raises(VoiceChatError):
        _read_exact(DribbleResp(b"x" * 10), 44)


def test_read_chunk_wraps_socket_stall():
    class StallResp:
        def read(self, n):
            raise TimeoutError("timed out")

    with pytest.raises(VoiceChatError, match="interrupted"):
        read_chunk(StallResp(), 4096)


def test_parse_wav_header():
    assert _parse_wav_header(wav_header(24000, 1)) == (24000, 1)


def test_parse_wav_header_implausible_raises():
    with pytest.raises(VoiceChatError):
        _parse_wav_header(wav_header(999, 1))
    with pytest.raises(VoiceChatError):
        _parse_wav_header(wav_header(24000, 0))


def make_client(**overrides):
    cfg = {"base_url": "http://localhost:3000", "email": "e@example.com",
           "password": "pw", **overrides}
    return VoiceChatClient(cfg)


def test_base_url_parsing():
    c = make_client(base_url="http://box:8123/aiui/")
    assert (c.host, c.port, c.prefix) == ("box", 8123, "/aiui")
    assert make_client(base_url="http://box").port == 80


def test_https_rejected():
    with pytest.raises(VoiceChatError):
        make_client(base_url="https://box")


def fake_resp(status=200, headers=None, body=b""):
    resp = MagicMock()
    resp.status = status
    state = {"body": body}

    def read(n=None):
        n = len(state["body"]) if n is None else n
        chunk, state["body"] = state["body"][:n], state["body"][n:]
        return chunk

    resp.read.side_effect = read
    resp.getheader.side_effect = lambda name, default=None: (headers or {}).get(name, default)
    return resp


def install_conns(mock_cls, *resps):
    """Each HTTPConnection() gets the next canned response; returns the conns."""
    conns = []
    resp_iter = iter(resps)

    def factory(*args, **kwargs):
        conn = MagicMock()
        conn.getresponse.return_value = next(resp_iter)
        conns.append(conn)
        return conn

    mock_cls.side_effect = factory
    return conns


LOGIN_OK = {"status": 200, "headers": {"Authorization": "Bearer tok123"}}


@patch("voice_chat.client.HTTPConnection")
def test_chat_logs_in_then_streams(mock_conn_cls):
    conns = install_conns(
        mock_conn_cls,
        fake_resp(**LOGIN_OK),
        fake_resp(200, {"X-Conversation-Id": "42"}, wav_header(24000, 1) + b"pcm"),
    )
    c = make_client()
    resp, rate, channels, conv = c.chat("hello")
    assert (rate, channels, conv) == (24000, 1, "42")
    assert resp.read(3) == b"pcm"
    assert conns[0].request.call_args.args[:2] == ("POST", "/api/login")
    chat_call = conns[1].request.call_args
    assert chat_call.args[:2] == ("POST", "/api/voice_chat")
    assert chat_call.kwargs["headers"]["Authorization"] == "Bearer tok123"
    c.close()
    conns[1].close.assert_called_once()
    c.close()                                # idempotent
    conns[1].close.assert_called_once()


@patch("voice_chat.client.HTTPConnection")
def test_expired_token_relogs_in_once(mock_conn_cls):
    conns = install_conns(
        mock_conn_cls,
        fake_resp(401),
        fake_resp(**LOGIN_OK),
        fake_resp(200, {"X-Conversation-Id": "7"}, wav_header()),
    )
    c = make_client()
    c.token = "stale"
    resp, rate, channels, conv = c.chat("hi", conversation_id="7")
    assert conv == "7"
    assert conns[0].close.called             # 401 connection torn down
    assert conns[1].request.call_args.args[1] == "/api/login"
    assert conns[2].request.call_args.kwargs["headers"]["Authorization"] == "Bearer tok123"


@patch("voice_chat.client.HTTPConnection")
def test_second_401_raises(mock_conn_cls):
    install_conns(mock_conn_cls, fake_resp(401), fake_resp(**LOGIN_OK), fake_resp(401))
    c = make_client()
    c.token = "stale"
    with pytest.raises(VoiceChatError, match="401"):
        c.chat("hi")


@patch("voice_chat.client.HTTPConnection")
def test_non_200_raises(mock_conn_cls):
    install_conns(mock_conn_cls, fake_resp(**LOGIN_OK), fake_resp(500, body=b"boom"))
    with pytest.raises(VoiceChatError, match="500"):
        make_client().chat("hi")


@patch("voice_chat.client.HTTPConnection")
def test_connection_refused_raises(mock_conn_cls):
    conn = MagicMock()
    conn.request.side_effect = ConnectionRefusedError("refused")
    mock_conn_cls.return_value = conn
    with pytest.raises(VoiceChatError, match="refused"):
        make_client().login()
    conn.close.assert_called_once()


@patch("voice_chat.client.HTTPConnection")
def test_login_failure_status_raises(mock_conn_cls):
    install_conns(mock_conn_cls, fake_resp(401))
    with pytest.raises(VoiceChatError, match="login failed"):
        make_client().login()


@patch("voice_chat.client.HTTPConnection")
def test_truncated_wav_header_raises_and_closes(mock_conn_cls):
    conns = install_conns(mock_conn_cls, fake_resp(**LOGIN_OK),
                          fake_resp(200, body=b"short"))
    with pytest.raises(VoiceChatError, match="ended after"):
        make_client().chat("hi")
    conns[1].close.assert_called_once()


@patch("voice_chat.client.HTTPConnection")
def test_optional_fields_sent_when_configured(mock_conn_cls):
    import json
    conns = install_conns(mock_conn_cls, fake_resp(**LOGIN_OK),
                          fake_resp(200, body=wav_header()))
    c = make_client(voice="nova", speed=1.2, model_code="fast")
    c.chat("hi", conversation_id="9")
    body = json.loads(conns[1].request.call_args.kwargs["body"])
    assert body == {"text": "hi", "conversation_id": "9", "voice": "nova",
                    "speed": 1.2, "model_code": "fast"}
