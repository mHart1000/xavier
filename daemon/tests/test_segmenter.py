"""Segmenter boundary logic, exercised with synthetic frames (no audio)."""

from audio.segmenter import Segmenter

SILENCE = b"\x00\x00"
SPEECH = b"\x11\x11"


def make_segmenter():
    # frame_ms=100 -> pre_roll=2, min_speech=3, end_silence=3, max=10 frames.
    return Segmenter(frame_ms=100, pre_roll_ms=200, min_speech_ms=300,
                     end_silence_ms=300, max_segment_seconds=1.0)


def feed_all(seg, frames):
    result = None
    for frame, is_speech in frames:
        out = seg.feed(frame, is_speech)
        if out is not None:
            result = out
    return result


def test_short_noise_rejected():
    seg = make_segmenter()
    # 1 speech frame then enough silence to finalize: below min_speech -> dropped.
    out = feed_all(seg, [(SPEECH, True), (SILENCE, False), (SILENCE, False), (SILENCE, False)])
    assert out is None


def test_valid_utterance_finalizes_on_silence():
    seg = make_segmenter()
    frames = [(SPEECH, True)] * 5 + [(SILENCE, False)] * 3
    out = feed_all(seg, frames)
    assert out is not None
    assert len(out) == 8 * len(SPEECH)  # 5 speech + 3 trailing silence frames


def test_pre_roll_captured():
    seg = make_segmenter()
    # Two silence frames fill pre-roll, then speech begins.
    frames = [(SILENCE, False), (SILENCE, False)] + [(SPEECH, True)] * 4 + [(SILENCE, False)] * 3
    out = feed_all(seg, frames)
    assert out is not None
    assert out.startswith(SILENCE)  # pre-roll audio prepended


def test_max_segment_force_cut():
    seg = make_segmenter()
    # Continuous speech with no trailing silence still cuts at max_frames (10).
    out = feed_all(seg, [(SPEECH, True)] * 12)
    assert out is not None
    assert len(out) == 10 * len(SPEECH)


def test_resets_between_utterances():
    seg = make_segmenter()
    first = feed_all(seg, [(SPEECH, True)] * 5 + [(SILENCE, False)] * 3)
    second = feed_all(seg, [(SPEECH, True)] * 5 + [(SILENCE, False)] * 3)
    assert first is not None and second is not None
    assert len(first) == len(second)
