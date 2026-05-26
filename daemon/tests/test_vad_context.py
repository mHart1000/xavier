"""
Silero VAD context-window handling — regression guard for the v5 bug where a
bare 512-sample frame (no carried context) makes the model output ~0 on real
speech. The model must receive context_size + window samples per call, with the
tail of each frame carried into the next. onnxruntime is faked so no model or
audio hardware is needed.
"""

import sys
import types

import numpy as np

from audio.vad import SileroVad, window_size, context_size


class _FakeInput:
    def __init__(self, name, shape):
        self.name = name
        self.shape = shape


class _FakeSession:
    """Records the 'input' tensor handed to each run() call."""

    def __init__(self, *args, **kwargs):
        self.fed_inputs = []

    def get_inputs(self):
        return [
            _FakeInput("input", ["batch", "samples"]),
            _FakeInput("state", [2, "batch", 128]),
            _FakeInput("sr", []),
        ]

    def run(self, _outputs, feed):
        self.fed_inputs.append(feed["input"])
        prob = np.array([[0.0]], dtype=np.float32)
        state = np.zeros((2, 1, 128), dtype=np.float32)
        return [prob, state]


def _vad_with_fake_session(monkeypatch):
    session = _FakeSession()
    fake_ort = types.ModuleType("onnxruntime")
    fake_ort.InferenceSession = lambda *a, **k: session
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    vad = SileroVad("dummy.onnx", sample_rate=16000)
    vad.load()
    return vad, session


def _frame(values):
    return np.asarray(values, dtype=np.int16).tobytes()


def test_input_includes_context(monkeypatch):
    vad, session = _vad_with_fake_session(monkeypatch)
    vad.is_speech(_frame(np.ones(window_size(16000)) * 1000))
    fed = session.fed_inputs[0]
    assert fed.shape == (1, window_size(16000) + context_size(16000))  # 1 x 576


def test_context_carries_between_frames(monkeypatch):
    vad, session = _vad_with_fake_session(monkeypatch)
    win, ctx = window_size(16000), context_size(16000)
    vad.is_speech(_frame(np.arange(win)))
    vad.is_speech(_frame(np.arange(win) + 5000))
    # The tail of frame 1 must reappear as the head of frame 2's input.
    first_tail = session.fed_inputs[0][0, -ctx:]
    second_head = session.fed_inputs[1][0, :ctx]
    np.testing.assert_allclose(second_head, first_tail)


def test_reset_clears_context(monkeypatch):
    vad, session = _vad_with_fake_session(monkeypatch)
    ctx = context_size(16000)
    vad.is_speech(_frame(np.ones(window_size(16000)) * 1000))
    vad.reset()
    vad.is_speech(_frame(np.ones(window_size(16000)) * 1000))
    # After reset the prepended context is zeros again.
    np.testing.assert_allclose(session.fed_inputs[-1][0, :ctx], np.zeros(ctx))
