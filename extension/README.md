# Xavier Firefox Extension

Privacy-first voice control extension for Firefox, communicating with a local daemon via Native Messaging.

## Structure

- `manifest.json` - Extension manifest with permissions and configuration
- `background/background.js` - Background script handling native messaging and browser actions
- `content/content.js` - Content script executing page-level actions and hint overlays

## Features 

### Navigation
- Back, forward, reload

### Scrolling
- Scroll up/down
- Page up/down
- Jump to top/bottom

### Tabs
- New tab, close tab
- Next/previous tab

### Hint-Based Clicking
- Show hints overlay on clickable elements
- Click elements by hint label (e.g., "AF", "B7")
- Hide hints

## Protocol

The extension communicates with the local daemon using the protocol defined in `/protocol/protocol.md`.

All commands follow the envelope format:
```json
{
  "type": "command",
  "id": "unique-id",
  "name": "command_name",
  "args": {},
  "meta": {}
}
```

## Privacy

- No cloud communication
- No telemetry
- All processing done locally
- Native Messaging for daemon communication (no network)
