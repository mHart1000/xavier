#!/bin/bash

# Xavier Native Messaging Host Installer for Linux
# Registers the native messaging host with Firefox

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_FILE="$SCRIPT_DIR/com.xavier.voice_browser.json"
TARGET_DIR="$HOME/.mozilla/native-messaging-hosts"

echo "Xavier Native Messaging Host Installer"
echo "======================================="
echo

# Check if manifest exists
if [ ! -f "$MANIFEST_FILE" ]; then
    echo "Error: Manifest file not found at $MANIFEST_FILE"
    exit 1
fi

# Check if launcher script exists and is executable
LAUNCHER_SCRIPT="$SCRIPT_DIR/xavier-daemon.sh"
if [ ! -f "$LAUNCHER_SCRIPT" ]; then
    echo "Error: Launcher script not found at $LAUNCHER_SCRIPT"
    exit 1
fi

if [ ! -x "$LAUNCHER_SCRIPT" ]; then
    echo "Error: Launcher script is not executable. Run: chmod +x $LAUNCHER_SCRIPT"
    exit 1
fi

# Create target directory if it doesn't exist
if [ ! -d "$TARGET_DIR" ]; then
    echo "Creating directory: $TARGET_DIR"
    mkdir -p "$TARGET_DIR"
fi

# Copy manifest to target location
echo "Installing native messaging host manifest..."
cp "$MANIFEST_FILE" "$TARGET_DIR/"

echo
echo "Installation complete!"
echo
echo "Manifest installed to: $TARGET_DIR/com.xavier.voice_browser.json"
echo "Launcher script: $LAUNCHER_SCRIPT"
echo
echo "You can now load the extension in Firefox from about:debugging"
echo
