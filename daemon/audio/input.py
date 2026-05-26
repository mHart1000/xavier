"""
Microphone capture via sounddevice. Frames (int16 PCM bytes) are pushed onto a
thread-safe queue by the audio callback and consumed by the listener thread.
Frame size matches the VAD window so each frame is one VAD step.
"""

import logging
import queue

logger = logging.getLogger(__name__)


class AudioInput:

    def __init__(self, sample_rate=16000, channels=1, frame_samples=512):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_samples = frame_samples
        self.queue = queue.Queue()
        self.stream = None

    def _callback(self, indata, frames, time_info, status):
        if status:
            logger.warning("audio input status: %s", status)
        self.queue.put(bytes(indata))

    def start(self):
        import sounddevice as sd

        try:
            self.stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.frame_samples,
                channels=self.channels,
                dtype="int16",
                callback=self._callback,
            )
            self.stream.start()
            logger.info("Microphone open (%d Hz, %d-sample frames)",
                        self.sample_rate, self.frame_samples)
        except Exception as e:
            raise RuntimeError(f"Could not open microphone: {e}") from e

    def frames(self):
        """Yield PCM frames until stop() enqueues the sentinel."""
        while True:
            frame = self.queue.get()
            if frame is None:
                return
            yield frame

    def stop(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.queue.put(None)  # unblock frames()
