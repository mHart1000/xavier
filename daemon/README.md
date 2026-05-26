# Xavier Voice Browser Daemon

The local voice control daemon for Xavier. Handles offline speech recognition and communicates with the browser extension via Native Messaging.

## Architecture

- **main.py** - Entry point and main loop
- **native_messaging/** - Firefox Native Messaging protocol implementation
- **core/** - Command parsing and STT interface
- **platform/** - OS-specific functionality (Windows/Linux/macOS)
- **config.json** - Configuration (STT model, audio settings)

## Installation

1. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Download Vosk model:
```bash
mkdir -p models
cd models
# Download lightweight English model
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
mv vosk-model-small-en-us-0.15 vosk-en
cd ..
```

## Running

In normal use the daemon is launched automatically by the browser extension via Native Messaging; you do not start it by hand.

To run it directly for debugging (it will block waiting for length-prefixed messages on stdin):
```bash
python main.py
```

Command names emitted by the parser follow [../protocol/protocol.md](../protocol/protocol.md), which is the source of truth shared with the extension.

## Privacy

All audio processing happens locally. No cloud APIs. No telemetry.
