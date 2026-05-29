#!/bin/bash

# Xavier Native Messaging Host Installer for Linux
# Registers the native messaging host with Firefox (deb/tarball, Snap, and Flatpak).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER_SCRIPT="$SCRIPT_DIR/xavier-daemon.sh"
HOST_NAME="com.xavier.voice_browser"
EXTENSION_ID="xavier@local"

echo "Xavier Native Messaging Host Installer"
echo "======================================="
echo

if [ ! -x "$LAUNCHER_SCRIPT" ]; then
    echo "Error: Launcher script missing or not executable: $LAUNCHER_SCRIPT"
    echo "Run: chmod +x $LAUNCHER_SCRIPT"
    exit 1
fi

# Generate the manifest with the launcher's absolute path on THIS machine, so the
# repo never carries a hard-coded personal path and the install is portable.
MANIFEST_JSON=$(cat <<EOF
{
  "name": "$HOST_NAME",
  "description": "Xavier voice browser control daemon",
  "path": "$LAUNCHER_SCRIPT",
  "type": "stdio",
  "allowed_extensions": [
    "$EXTENSION_ID"
  ]
}
EOF
)

# Firefox reads native-messaging host manifests from a different directory for each
# packaging format. Install into every location whose base directory exists, so this
# works regardless of how Firefox was installed:
#   deb/tarball : ~/.mozilla/native-messaging-hosts
#   Snap        : ~/snap/firefox/common/.mozilla/native-messaging-hosts
#   Flatpak     : ~/.var/app/org.mozilla.firefox/.mozilla/native-messaging-hosts
declare -a TARGET_DIRS=("$HOME/.mozilla/native-messaging-hosts")
SNAP_FOUND=0
if [ -d "$HOME/snap/firefox" ]; then
    TARGET_DIRS+=("$HOME/snap/firefox/common/.mozilla/native-messaging-hosts")
    SNAP_FOUND=1
fi
if [ -d "$HOME/.var/app/org.mozilla.firefox" ]; then
    TARGET_DIRS+=("$HOME/.var/app/org.mozilla.firefox/.mozilla/native-messaging-hosts")
fi

for dir in "${TARGET_DIRS[@]}"; do
    mkdir -p "$dir"
    printf '%s\n' "$MANIFEST_JSON" > "$dir/$HOST_NAME.json"
    echo "Installed manifest -> $dir/$HOST_NAME.json"
done

echo
echo "Installation complete!"
echo "Launcher script: $LAUNCHER_SCRIPT"
echo

if [ "$SNAP_FOUND" -eq 1 ]; then
    echo "Snap Firefox detected — two confinement caveats:"
    echo "  - The daemon must live in a NON-hidden path under \$HOME (yours does:"
    echo "    $SCRIPT_DIR). Snap's 'home' interface cannot see dotfile-hidden dirs."
    echo "  - Microphone capture relies on Firefox's 'audio-record' Snap interface."
    echo "    If the mic is silent, check: snap connections firefox | grep audio-record"
    echo
fi

echo "Next: load the extension in Firefox at about:debugging#/runtime/this-firefox"
echo "(Load Temporary Add-on -> select extension/manifest.json)"
echo
