"""
Silero VAD over onnxruntime (no PyTorch). Loads the silero_vad.onnx model and
returns a per-frame speech probability. Silero v5 expects a fixed window of 512
samples at 16 kHz (256 at 8 kHz); frames are sized to match upstream.

The ONNX I/O (input/output names, state shape) follows silero v5. Names are
resolved dynamically where possible; verify with --mic-test if the bundled
model version differs.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

_STATE_SHAPE = (2, 1, 128)


def window_size(sample_rate):
    return 512 if sample_rate >= 16000 else 256


class SileroVad:

    def __init__(self, model_path, sample_rate=16000, threshold=0.5):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.window = window_size(sample_rate)
        self.session = None
        self._sr_name = None
        self._state_name = None
        self._input_name = None
        self.state = np.zeros(_STATE_SHAPE, dtype=np.float32)

    def load(self):
        import onnxruntime as ort

        logger.info("Loading Silero VAD model from %s", self.model_path)
        self.session = ort.InferenceSession(
            self.model_path, providers=["CPUExecutionProvider"]
        )
        # Map input tensors by shape/name: scalar int64 -> sr, 3-D -> state, else audio.
        for inp in self.session.get_inputs():
            name = inp.name
            if name == "sr" or "sr" in name.lower():
                self._sr_name = name
            elif len(inp.shape) == 3 or "state" in name.lower():
                self._state_name = name
            else:
                self._input_name = name
        logger.info("Silero VAD loaded (window=%d)", self.window)

    def is_speech(self, frame_bytes):
        """Return speech probability [0, 1] for one frame of int16 PCM."""
        if self.session is None:
            return 0.0

        audio = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio) < self.window:
            audio = np.pad(audio, (0, self.window - len(audio)))
        elif len(audio) > self.window:
            audio = audio[:self.window]

        feed = {self._input_name: audio[np.newaxis, :].astype(np.float32)}
        if self._state_name:
            feed[self._state_name] = self.state
        if self._sr_name:
            feed[self._sr_name] = np.array(self.sample_rate, dtype=np.int64)

        results = self.session.run(None, feed)
        prob = float(np.asarray(results[0]).reshape(-1)[0])
        if self._state_name and len(results) > 1:
            self.state = results[1]
        return prob

    def reset(self):
        """Clear recurrent state between utterances."""
        self.state = np.zeros(_STATE_SHAPE, dtype=np.float32)
