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

## Current Phase: Phase 3 (Skeleton)

The daemon currently:
- ✓ Has proper directory structure
- ✓ Implements Native Messaging framing
- ✓ Includes command parser stub
- ✓ Sends hardcoded test commands
- ✗ Does not yet do STT (Phase 6)
- ✗ Does not yet capture audio (Phase 6)

## Running

```bash
python main.py
```

For production use, the daemon will be launched by the browser extension via Native Messaging.

## Privacy

All audio processing happens locally. No cloud APIs. No telemetry.
