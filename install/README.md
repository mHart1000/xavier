# Native Messaging Installation

This directory contains the native messaging host configuration for Linux.

## Files

- **com.xavier.voice_browser.json**: Native messaging host manifest
- **xavier-daemon.sh**: Launcher script that Firefox calls to start the daemon
- **install.sh**: Installation script that registers the host with Firefox

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

## Testing

To test the native messaging connection:
1. Open Firefox developer console (Ctrl+Shift+J)
2. Load the extension
3. Check for connection messages in the console
4. The daemon should print messages to stderr (visible when run from terminal)

## Uninstallation

To remove the native messaging host:
```bash
rm ~/.mozilla/native-messaging-hosts/com.xavier.voice_browser.json
```

## Troubleshooting

If the connection fails:
- Check that `xavier-daemon.sh` is executable
- Verify the path in the manifest points to the correct launcher script
- Check Firefox Browser Console for error messages
- Run the daemon manually to test: `./xavier-daemon.sh`
