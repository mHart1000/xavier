"""
Microphone capture via a subprocess that streams raw s16le PCM on stdout.

PortAudio/sounddevice's ALSA->PipeWire path returns near-DC garbage on some
systems (looks like audio by amplitude, but has no speech content), so we read
from the system's own capture tool instead: parecord (PulseAudio / pipewire-pulse)
or pw-record (native PipeWire). Frames (int16 PCM bytes) are pushed onto a
thread-safe queue by a reader thread and consumed by the listener thread.
Frame size matches the VAD window so each frame is one VAD step.
"""

import logging
import queue
import shutil
import subprocess
import threading

logger = logging.getLogger(__name__)


def _default_command(sample_rate, channels, source):
    """Build a raw-PCM capture command from whatever tool is available."""
    if shutil.which("parecord"):
        cmd = ["parecord", f"--rate={sample_rate}", f"--channels={channels}",
               "--format=s16le", "--raw", "--latency-msec=30"]
        if source:
            cmd.append(f"--device={source}")
        return cmd
    if shutil.which("pw-record"):
        cmd = ["pw-record", f"--rate={sample_rate}", f"--channels={channels}",
               "--format=s16"]
        if source:
            cmd += ["--target", source]
        cmd.append("-")  # write raw PCM to stdout
        return cmd
    raise RuntimeError(
        "No audio capture tool found. Install pulseaudio-utils (parecord) "
        "or pipewire (pw-record), or set audio.capture_command in config.json."
    )


class AudioInput:

    def __init__(self, sample_rate=16000, channels=1, frame_samples=512,
                 source=None, command=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_samples = frame_samples
        self.frame_bytes = frame_samples * channels * 2  # int16
        self.source = source        # pulse source name; None = system default
        self.command = command      # explicit arg-list override; None = auto-detect
        self.queue = queue.Queue()
        self.proc = None
        self.reader = None
        self._stop = threading.Event()

    def start(self):
        cmd = self.command or _default_command(
            self.sample_rate, self.channels, self.source)
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except (FileNotFoundError, OSError) as e:
            raise RuntimeError(f"Could not start capture command {cmd!r}: {e}") from e

        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()
        logger.info("Microphone open via %s (%d Hz, %d-sample frames)",
                    cmd[0], self.sample_rate, self.frame_samples)

    def _read_loop(self):
        stream = self.proc.stdout
        while not self._stop.is_set():
            chunk = stream.read(self.frame_bytes)
            if not chunk or len(chunk) < self.frame_bytes:
                break  # EOF or short read on shutdown
            self.queue.put(chunk)
        self.queue.put(None)  # unblock frames()

    def frames(self):
        """Yield PCM frames until stop() (or EOF) enqueues the sentinel."""
        while True:
            frame = self.queue.get()
            if frame is None:
                return
            yield frame

    def stop(self):
        self._stop.set()
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
        self.queue.put(None)  # ensure frames() returns even if reader already exited
