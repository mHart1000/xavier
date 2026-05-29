# Xavier Voice Browser Daemon

The local voice control daemon for Xavier. Captures microphone audio, performs
offline speech-to-text, turns transcripts into deterministic commands, and sends
them to the browser extension via Native Messaging.

## Architecture

```
main.py              Entry point + Native Messaging loop; starts the Listener on `ready`
core/
  config.py          Loads config.json over defaults; resolves model paths
  listener.py        Pipeline thread: input -> VAD -> segmenter -> STT -> activation -> parser -> emit
  activation_policy.py  Wake-phrase handling, session state, risk-tier gating, confirmation
  parser.py          Transcript -> structured protocol command (deterministic)
audio/
  input.py           Microphone capture (parecord/pw-record subprocess), 16 kHz mono int16 frames
  vad.py             Silero VAD via onnxruntime (per-frame speech probability)
  segmenter.py       Pre-roll / min-speech / end-silence / max-segment utterance cutting
stt/
  base.py            SpeechRecognizer interface + Transcript + factory (with fallback)
  hybrid_recognizer.py   Default: grammar-constrained Vosk fast path + Whisper accuracy path
  whisper_recognizer.py  Accuracy path / fallback: faster-whisper
  vosk_recognizer.py     Fast path (grammar-constrained); also a plain fallback engine
native_messaging/
  framing.py         Firefox Native Messaging length-prefixed framing
platform/            OS-specific host registration
config.json          STT engine, audio, VAD, listener, and safety settings
```

The STT engine is pluggable: the rest of the system only sees transcripts, and
the extension only sees structured commands. See
[../protocol/protocol.md](../protocol/protocol.md) for the command contract
(unchanged by STT).

The default `hybrid` engine runs a grammar-constrained Vosk recognizer on every
utterance (fast: ~0.6s end-to-end for the fixed command set) and, when the
transcript begins with a trigger such as "open url", re-transcribes the audio
with Whisper for open-vocabulary accuracy (~1s). Out-of-grammar speech is
rejected. Set `stt.engine` to `whisper` or `vosk` for a single-engine setup.

## Installation

0. Audio capture uses a system tool, not a Python library (PortAudio/sounddevice's
PipeWire path returns silent/DC-garbage audio on some Linux systems). Install one of:
```bash
sudo apt install pulseaudio-utils   # provides parecord (works on PulseAudio + PipeWire)
# or, on a PipeWire system, pw-record ships with the pipewire package
```

1. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Download the Silero VAD model:
```bash
mkdir -p models
curl -L -o models/silero_vad.onnx \
  https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx
```

4. Whisper model: faster-whisper downloads `base.en` (~150 MB) into
`models/whisper/` automatically on first run, then runs fully offline. No manual
step is required.

5. Vosk model — **required** for the default `hybrid` engine (also used as the
plain `vosk` fallback engine):
```bash
cd models
curl -L -O https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip && mv vosk-model-small-en-us-0.15 vosk-en
cd ..
```

## Running

In normal use the daemon is launched automatically by the browser extension via
Native Messaging; you do not start it by hand.

To exercise the speech pipeline **without** Firefox (commands print to stderr):
```bash
python main.py --mic-test
```
Speak a command, pause, and watch the parsed command appear. Ctrl-C to stop.

Capture reads from the system default source. To use a specific microphone, list
sources and set `audio.capture_source` in `config.json` to a source name:
```bash
python main.py --list-devices      # = pactl list sources short
# e.g. "audio": { "capture_source": "alsa_input.usb-Razer_Kiyo_Pro-02.analog-stereo" }
```
For non-Pulse/PipeWire setups, override the whole command with
`audio.capture_command` (an arg list emitting raw s16le PCM on stdout).

Tests (no microphone or models needed):
```bash
python -m pytest tests
```

## Logs

The daemon logs to **stderr** and to a file at the repo root, `logs/xavier.log`
(set by `logging.file` in `config.json`). When Firefox launches the daemon its
stderr is usually not visible (especially under Snap), so tail the file:
```bash
tail -f ../logs/xavier.log
```

## Listener modes & safety tiers

`config.json` configures listener behavior and safety independently of the STT
engine.

Listener modes (`listener.mode`):
- `vad_continuous` *(default)* — VAD gates the expensive STT; any valid command
  runs. Optionally prefix with the wake phrase to (re)activate a session.
- `push_to_talk` — capture is gated externally; each utterance is in-session.
- `wake_required`, `wake_then_session`, `adaptive_wake` — defined but not yet
  implemented; selecting one fails fast at startup.

Command risk tiers (enforced in `activation_policy.py`):
- **Low** (scroll, page, jump, hints, focus page) — allowed in an active session.
- **Medium** (back/forward/reload, tab nav, hint click, focus address) — require
  an active session.
- **High** (close tab, open URL) — require a spoken **"confirm"** first when
  `safety.confirm_high_risk_commands` is set.

There are no inferential clicks and no form submission: clicking is only ever by
explicit hint label.

## Privacy

All audio processing happens locally. No cloud STT, no telemetry. The only
network access is the **one-time** model download at setup (Whisper + Silero);
after that the daemon runs fully offline.
