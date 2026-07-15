"""
Audio playback via a subprocess that reads raw s16le PCM on stdin.

Mirrors audio/input.py: instead of adding an audio dependency we feed the
system's own playback tool — paplay (PulseAudio / pipewire-pulse) or
pw-play/pw-cat (native PipeWire). bufsize=0 keeps writes on the OS pipe, so a
full pipe blocks the writer and streaming naturally runs at playback speed.
"""

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def _default_playback_command(sample_rate, channels):
    """Build a raw-PCM playback command from whatever tool is available."""
    if shutil.which("paplay"):
        return ["paplay", "--raw", f"--rate={sample_rate}",
                f"--channels={channels}", "--format=s16le"]
    if shutil.which("pw-play"):
        return ["pw-play", "--rate", str(sample_rate), "--channels", str(channels),
                "--format", "s16", "-"]
    if shutil.which("pw-cat"):
        return ["pw-cat", "--playback", "--rate", str(sample_rate),
                "--channels", str(channels), "--format", "s16", "-"]
    raise RuntimeError(
        "No audio playback tool found. Install pulseaudio-utils (paplay) "
        "or pipewire (pw-play), or set voice_chat.playback_command in config.json."
    )


class AudioOutput:

    def __init__(self, sample_rate, channels=1, command=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.command = command      # explicit arg-list override; None = auto-detect
        self.proc = None

    def start(self):
        cmd = self.command or _default_playback_command(self.sample_rate, self.channels)
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, bufsize=0,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (FileNotFoundError, OSError) as e:
            raise RuntimeError(f"Could not start playback command {cmd!r}: {e}") from e
        logger.info("Playback open via %s (%d Hz, %d ch)",
                    cmd[0], self.sample_rate, self.channels)

    def write(self, data):
        try:
            self.proc.stdin.write(data)
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"Playback process died: {e}") from e

    def close(self):
        """EOF stdin and let the player drain buffered audio (keeps the speech tail)."""
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._kill()
        self.proc = None

    def abort(self):
        """Stop immediately, dropping buffered audio."""
        if self.proc is None:
            return
        self._kill()
        self.proc = None

    def _kill(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
