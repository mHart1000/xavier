# Native Messaging Installation

This directory contains the native messaging host configuration for Linux.

## Files

- **com.xavier.voice_browser.json**: Template manifest (reference for manual installs;
  `install.sh` generates the real one with the correct absolute path)
- **xavier-daemon.sh**: Launcher script that Firefox calls to start the daemon
- **install.sh**: Installer — generates the manifest and registers the host with Firefox
  (deb/tarball, Snap, and Flatpak locations)

## Installation Steps

1. Make sure the daemon virtual environment is set up:
   ```bash
   cd ../daemon
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Run the installer:
   ```bash
   cd ../install
   ./install.sh
   ```

3. Load the extension in Firefox:
   - Open `about:debugging#/runtime/this-firefox`
   - Click "Load Temporary Add-on"
   - Select the `manifest.json` file from the `extension/` directory

## Firefox packaging matters (Snap / Flatpak)

Firefox reads native-messaging host manifests from a **different directory depending on
how it was installed**. `install.sh` detects this and installs to every applicable path:

| Packaging        | Manifest directory |
|------------------|--------------------|
| deb / tarball    | `~/.mozilla/native-messaging-hosts/` |
| **Snap** (Ubuntu default) | `~/snap/firefox/common/.mozilla/native-messaging-hosts/` |
| Flatpak          | `~/.var/app/org.mozilla.firefox/.mozilla/native-messaging-hosts/` |

To check which one you have: `snap list firefox` (Snap) or `flatpak list | grep firefox`
(Flatpak); otherwise it's the deb/tarball build.

### Snap confinement caveats

Snap Firefox runs sandboxed, and any program it launches (our daemon) inherits that
confinement. Two consequences:

- **The daemon must live in a non-hidden path under `$HOME`.** Snap's `home` interface
  exposes only non-dotfile paths in your home directory. A project at
  `~/dev/xavier/...` works; one at `~/.local/share/xavier/...` would be invisible and
  the launch would fail silently.
- **Microphone access depends on Firefox's `audio-record` interface.** It's connected by
  default; if the mic is silent under Firefox but `daemon --mic-test` works, verify:
  ```bash
  snap connections firefox | grep audio-record
  ```

A missing manifest produces **no error** — Firefox just behaves as if the host doesn't
exist. If native messaging "does nothing," the manifest path is the first thing to check.

## Testing

To see the daemon's logs, **fully quit Firefox first**, then launch it from a terminal
(otherwise `firefox` just opens a tab in the running instance and you won't capture the
daemon's stderr):

```bash
firefox
```

Then load the extension. The daemon prints model loading and, once ready,
`Listener started (mode=vad_continuous)`. The Browser Console (Ctrl+Shift+J) shows
extension-side connection errors.

## Uninstallation

Remove the manifest from whichever locations exist:
```bash
rm -f ~/.mozilla/native-messaging-hosts/com.xavier.voice_browser.json
rm -f ~/snap/firefox/common/.mozilla/native-messaging-hosts/com.xavier.voice_browser.json
rm -f ~/.var/app/org.mozilla.firefox/.mozilla/native-messaging-hosts/com.xavier.voice_browser.json
```

## Troubleshooting

If the connection fails:
- Confirm the manifest landed in the directory matching your Firefox packaging (see table above)
- Check that `xavier-daemon.sh` is executable
- Verify the `path` in the manifest points to the correct launcher script
- Check the Firefox Browser Console (Ctrl+Shift+J) for error messages
- Run the daemon manually to isolate the daemon from Firefox: `./xavier-daemon.sh`
