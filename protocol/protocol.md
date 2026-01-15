# Voice Browser Protocol Specification

## Overview

This protocol defines the JSON-based communication between the voice daemon and the Firefox extension via Native Messaging. The protocol is designed to be **stable** and **version-agnostic** to support future daemon implementations (e.g., Rust rewrite) without requiring extension changes.

---

## Transport Layer

**Native Messaging** over stdin/stdout:
- Each message is prefixed with a **4-byte little-endian unsigned integer** indicating the message length
- Message payload is **UTF-8 encoded JSON**
- No newline delimiters

---

## Message Envelope

All messages follow this structure:

```json
{
  "type": "command" | "ack" | "error" | "ping",
  "id": "string or number",
  "name": "command_name",
  "args": { ... },
  "meta": { ... }
}
```

### Fields

- **type** (required): Message type
  - `"command"` — Daemon → Extension: execute a browser action
  - `"ack"` — Extension → Daemon: command received/executed
  - `"error"` — Extension → Daemon: command failed
  - `"ping"` — Bidirectional: connection health check

- **id** (required): Unique message identifier for correlation (UUID or sequential integer)

- **name** (required for `command`): The command name (see Command Reference below)

- **args** (optional): Command-specific arguments (object)

- **meta** (optional): Metadata (e.g., STT confidence, raw transcript)

---

## Command Reference (MVP)

### Navigation Commands

#### `nav_back`
Navigate to the previous page in history.
```json
{
  "type": "command",
  "id": "1",
  "name": "nav_back",
  "args": {}
}
```

#### `nav_forward`
Navigate to the next page in history.
```json
{
  "type": "command",
  "id": "2",
  "name": "nav_forward",
  "args": {}
}
```

#### `nav_reload`
Reload the current page.
```json
{
  "type": "command",
  "id": "3",
  "name": "nav_reload",
  "args": {}
}
```

---

### Scrolling Commands

#### `scroll_up`
Scroll the page upward.
```json
{
  "type": "command",
  "id": "4",
  "name": "scroll_up",
  "args": {
    "amount": 200
  }
}
```
- `amount` (optional, default: 200): Pixels to scroll

#### `scroll_down`
Scroll the page downward.
```json
{
  "type": "command",
  "id": "5",
  "name": "scroll_down",
  "args": {
    "amount": 200
  }
}
```

#### `page_up`
Scroll up by one viewport height.
```json
{
  "type": "command",
  "id": "6",
  "name": "page_up",
  "args": {}
}
```

#### `page_down`
Scroll down by one viewport height.
```json
{
  "type": "command",
  "id": "7",
  "name": "page_down",
  "args": {}
}
```

---

### Jump Commands

#### `jump_top`
Jump to the top of the page.
```json
{
  "type": "command",
  "id": "8",
  "name": "jump_top",
  "args": {}
}
```

#### `jump_bottom`
Jump to the bottom of the page.
```json
{
  "type": "command",
  "id": "9",
  "name": "jump_bottom",
  "args": {}
}
```

---

### Tab Commands

#### `tab_new`
Open a new tab.
```json
{
  "type": "command",
  "id": "10",
  "name": "tab_new",
  "args": {}
}
```

#### `tab_close`
Close the current tab.
```json
{
  "type": "command",
  "id": "11",
  "name": "tab_close",
  "args": {}
}
```
⚠️ **Note**: May require confirmation in MVP to prevent accidental data loss.

#### `tab_next`
Switch to the next tab.
```json
{
  "type": "command",
  "id": "12",
  "name": "tab_next",
  "args": {}
}
```

#### `tab_prev`
Switch to the previous tab.
```json
{
  "type": "command",
  "id": "13",
  "name": "tab_prev",
  "args": {}
}
```

---

### Hint Commands

#### `hints_show`
Display clickable hint overlays on the page.
```json
{
  "type": "command",
  "id": "14",
  "name": "hints_show",
  "args": {}
}
```

#### `hints_hide`
Remove all hint overlays.
```json
{
  "type": "command",
  "id": "15",
  "name": "hints_hide",
  "args": {}
}
```

#### `hint_click`
Click the element associated with the specified hint code.
```json
{
  "type": "command",
  "id": "16",
  "name": "hint_click",
  "args": {
    "code": "AF"
  }
}
```
- `code` (required): Hint label (e.g., "AF", "B7")

---

### Focus Commands (Optional MVP)

#### `focus_address`
Focus the address bar.
```json
{
  "type": "command",
  "id": "17",
  "name": "focus_address",
  "args": {}
}
```

---

### URL Commands (Optional MVP)

#### `open_url`
Navigate to a URL.
```json
{
  "type": "command",
  "id": "18",
  "name": "open_url",
  "args": {
    "url": "https://example.com"
  }
}
```
- `url` (required): Full URL including protocol

---

## Response Messages

### Acknowledgment (ack)

Sent by the extension when a command is successfully received/executed.

```json
{
  "type": "ack",
  "id": "1",
  "ok": true
}
```

### Error

Sent by the extension when a command fails.

```json
{
  "type": "error",
  "id": "1",
  "message": "Unknown command: invalid_command"
}
```

- `message` (required): Human-readable error description

### Ping

Bidirectional health check.

```json
{
  "type": "ping",
  "id": "0"
}
```

Response:
```json
{
  "type": "ack",
  "id": "0",
  "ok": true
}
```

---

## Metadata Field

The `meta` object can include:

- **confidence** (float, 0.0–1.0): STT confidence score
- **raw** (string): Original transcript before parsing
- **timestamp** (ISO 8601 string): When the command was created

Example:
```json
{
  "type": "command",
  "id": "42",
  "name": "scroll_down",
  "args": {},
  "meta": {
    "confidence": 0.87,
    "raw": "scroll down",
    "timestamp": "2026-01-15T10:30:00Z"
  }
}
```

---

## Error Handling

- **Unknown command**: Extension responds with `{type: "error", message: "Unknown command: <name>"}`
- **Missing required args**: Extension responds with `{type: "error", message: "Missing required argument: <arg>"}`
- **Execution failure**: Extension responds with `{type: "error", message: "<specific error>"}`

---

## Protocol Stability

This protocol is **stable** and must remain backward-compatible. Changes must be:
- Additive (new commands, new optional fields)
- Never remove or rename existing commands
- Never change required argument names or types

Future versions may introduce a `"version"` field in the envelope if breaking changes are unavoidable.

---

## Implementation Notes

- **Daemon responsibilities**: Audio → STT → Intent parsing → JSON generation
- **Extension responsibilities**: JSON parsing → Browser action execution
- **No DOM logic in daemon**: All page interaction happens in the extension
- **No STT in extension**: All speech processing happens in the daemon

---

## Example Full Flow

1. **User speaks**: "scroll down"
2. **Daemon processes**:
   - Captures audio
   - Vosk transcribes → "scroll down"
   - Parser normalizes → `scroll_down`
   - Emits JSON:
     ```json
     {
       "type": "command",
       "id": "123",
       "name": "scroll_down",
       "args": {},
       "meta": {
         "confidence": 0.92,
         "raw": "scroll down"
       }
     }
     ```
3. **Extension receives** via Native Messaging
4. **Extension executes**: Injects content script, scrolls page
5. **Extension responds**:
   ```json
   {
     "type": "ack",
     "id": "123",
     "ok": true
   }
   ```

---

End of Protocol Specification v1.0
