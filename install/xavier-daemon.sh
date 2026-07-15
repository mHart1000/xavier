#!/bin/bash

# Xavier Voice Browser Daemon Launcher
# This script is called by Firefox Native Messaging

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DAEMON_DIR="$PROJECT_ROOT/daemon"

# Check if venv exists
if [ ! -d "$DAEMON_DIR/venv" ]; then
    echo "Error: Virtual environment not found at $DAEMON_DIR/venv" >&2
    exit 1
fi

# Load local secrets (voice-chat credentials) if present; gitignored.
set -a
[ -f "$DAEMON_DIR/.env" ] && . "$DAEMON_DIR/.env"
set +a

# Activate virtual environment and run daemon
cd "$DAEMON_DIR"
source venv/bin/activate
exec python main.py
