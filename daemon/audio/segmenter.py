"""
Utterance segmenter. Consumes (frame, is_speech) pairs and yields complete
utterances as int16 PCM bytes. Pure logic (no audio/model deps) so it is unit
testable with synthetic frame/flag sequences.

Behavior:
- pre-roll ring buffer captures audio just before speech starts
- min speech duration rejects tiny noises
- end-silence threshold finalizes an utterance
- max segment duration force-cuts runaway capture
"""

import collections


class Segmenter:

    def __init__(self, sample_rate=16000, frame_ms=32, pre_roll_ms=500,
                 min_speech_ms=300, end_silence_ms=700, max_segment_seconds=8):
        self.frame_ms = frame_ms
        self.pre_roll_frames = max(1, pre_roll_ms // frame_ms)
        self.min_speech_frames = max(1, min_speech_ms // frame_ms)
        self.end_silence_frames = max(1, end_silence_ms // frame_ms)
        self.max_frames = max(1, int(max_segment_seconds * 1000 // frame_ms))

        self.preroll = collections.deque(maxlen=self.pre_roll_frames)
        self.active = False
        self.buffer = []
        self.speech_frames = 0
        self.silence_run = 0

    def feed(self, frame, is_speech):
        """
        Feed one frame. Returns a finalized utterance (bytes) when complete and
        long enough, otherwise None.
        """
        if not self.active:
            self.preroll.append(frame)
            if is_speech:
                self.active = True
                self.buffer = list(self.preroll)
                self.preroll.clear()
                self.speech_frames = 1
                self.silence_run = 0
            return None

        self.buffer.append(frame)
        if is_speech:
            self.speech_frames += 1
            self.silence_run = 0
        else:
            self.silence_run += 1

        if self.silence_run >= self.end_silence_frames or len(self.buffer) >= self.max_frames:
            return self._finalize()
        return None

    def _finalize(self):
        long_enough = self.speech_frames >= self.min_speech_frames
        data = b"".join(self.buffer) if long_enough else None
        self.reset()
        return data

    def reset(self):
        self.active = False
        self.buffer = []
        self.speech_frames = 0
        self.silence_run = 0
        self.preroll.clear()
