"""Put the daemon directory on sys.path so tests can import core/audio/stt."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
