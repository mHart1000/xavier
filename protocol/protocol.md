# Xavier Voice Browser — Protocol Specification (v1.0)

## Overview

This document defines the JSON-based contract between the voice **daemon** and the Firefox **extension** over Native Messaging. The protocol is designed to be **stable** and **language-agnostic** so the daemon can be reimplemented (e.g., Python → Rust) without changing the extension.

Roles:
- **Daemon**: audio capture, speech-to-text, intent parsing, JSON command emission.
- **Extension**: JSON parsing, browser/page action execution.
- The daemon contains no DOM logic. The extension contains no STT.

---

## Transport

Native Messaging over the daemon process's stdin/stdout:
- Each message is prefixed by a **4-byte little-endian unsigned integer** giving the byte length of the JSON payload that follows.
- The payload is **UTF-8-encoded JSON**.
- No newline delimiters.

---

## Message Envelope

All messages share this structure:

```json
{
  "type": "command" | "ready" | "ack" | "error" | "ping" | "set_listening" | "exit_input_mode" | "input_mode",
  "id": "string",
  "name": "command_name",
  "args": { },
  "meta": { }
}
```

| Field  | Required for                       | Notes                                                    |
|--------|------------------------------------|----------------------------------------------------------|
| `type` | all messages                       | One of the values listed above.                          |
| `id`   | all messages                       | Unique identifier for correlation. UUID or sequence #.   |
| `name` | `command`                          | Canonical command name (see Command Reference).          |
| `args` | per-command (see reference)        | Object. Omit or `{}` if no arguments.                    |
| `meta` | optional on any message            | Free-form object. See Metadata.                          |

---

## Connection Lifecycle

1. The extension calls `browser.runtime.connectNative("com.xavier.voice_browser")`. Firefox spawns the daemon.
2. The extension sends a `ready` message announcing itself.
3. The daemon sends `command` messages; the extension replies with `ack` or `error` keyed off the command `id`.
4. Either side may send `ping`; the other replies with `ack` carrying the same `id`.
5. On EOF (Firefox closes the port, or the daemon exits), the other side cleans up. The extension may attempt reconnection.

---

## Command Reference (MVP)

All commands are sent **daemon → extension** with `type: "command"`.

### Navigation

| `name`         | `args` | Effect                              |
|----------------|--------|-------------------------------------|
| `nav_back`     | none   | History back in the active tab.     |
| `nav_forward`  | none   | History forward in the active tab.  |
| `nav_reload`   | none   | Reload the active tab.              |

### Scrolling

| `name`        | `args`                          | Effect                          |
|---------------|----------------------------------|---------------------------------|
| `scroll_up`   | `{ "amount": int }` (optional)  | Scroll up; default 200px.       |
| `scroll_down` | `{ "amount": int }` (optional)  | Scroll down; default 200px.     |
| `page_up`     | none                            | Scroll up by one viewport.      |
| `page_down`   | none                            | Scroll down by one viewport.    |

### Jump

| `name`        | `args` | Effect                       |
|---------------|--------|------------------------------|
| `jump_top`    | none   | Scroll to top of page.       |
| `jump_bottom` | none   | Scroll to bottom of page.    |

### Tabs

| `name`      | `args` | Effect                                                  |
|-------------|--------|---------------------------------------------------------|
| `tab_new`   | none   | Open a new empty tab.                                   |
| `tab_close` | none   | Close the active tab. *MVP-safe: see Safety §.*         |
| `tab_next`  | none   | Switch to the next tab (wraps).                         |
| `tab_prev`  | none   | Switch to the previous tab (wraps).                     |

### Hints

| `name`        | `args` | Effect                                                                                                                                |
|---------------|--------|--------------------------------------------------------------------------------------------------------------------------------------|
| `hints_show`  | none   | Label each visible clickable element with the spoken name used to target it (its visible text or first class name); repeats are numbered. |
| `links_show`  | none   | Label each visible clickable element with `link N` (1-based, document order); say "link N" to target it. Mutually exclusive with `hints_show` — showing either clears the other. |
| `hints_hide`  | none   | Remove the hint or link overlay.                                                                                                    |

### Text Targeting

Name an element by its visible text or first class name, then act on it (parallel to the hint flow).

| `name`             | `args`                  | Effect                                                                                  |
|--------------------|-------------------------|-----------------------------------------------------------------------------------------|
| `highlight_text`     | `{ "text": "expand", "ordinal": 3, "literal": "expand three" }` | Highlight the element matching `text` by visible text (substring) or exact first class name; set it as the active target. Optional `ordinal` (1-based) picks which match to start on; out of range clamps to the last. Optional `literal` is the full spoken phrase including a trailing number word — the extension tries it as a match first (so a real target ending in a number word wins) before falling back to `text` + `ordinal`. |
| `highlight_next`     | none                    | Move the highlight to the next element matching the current text (wraps).               |
| `highlight_previous` | none                    | Move the highlight to the previous element matching the current text (wraps).           |
| `link_select`        | `{ "number": N }`       | Select the Nth label from the most recent `links_show` (1-based) as the active target — highlights it; does not click. Errors if `number` is out of range. |
| `click`              | none                    | Click the active highlighted target, then clear the highlight.                          |
| `open_new_tab`       | none                    | Open the active highlighted target's link in a new background tab (focus stays on the current tab), then clear the highlight. |
| `clear_highlights`   | none                    | Remove the highlight and clear the active target.                                       |

### Focus

| `name`           | `args` | Effect                                                                      |
|------------------|--------|-----------------------------------------------------------------------------|
| `focus_address`  | none   | Focus the URL bar. May require an extra user gesture in some contexts.      |
| `focus_page`     | none   | Return keyboard focus to the page body. Required before `scroll_*` if the URL bar was previously focused. |

### Input

| `name`       | `args`                | Effect                                                                                                                                                                                          |
|--------------|-----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_text` | `{ "text": "..." }`   | Type `text` into the currently focused editable element (text `<input>`, `<textarea>`, or contenteditable), inserted at the caret. Casing/punctuation are preserved. Errors if none is focused. |

Sent while the daemon is in **input mode**, which the user enters by saying
"input" and leaves by saying "end input" or after a few seconds of silence. Each
dictated utterance arrives as its own `input_text` command; the extension is
stateless here and simply types what it receives.

### URL (optional MVP)

| `name`     | `args`                        | Effect                                  |
|------------|-------------------------------|-----------------------------------------|
| `open_url` | `{ "url": "https://..." }`    | Open the URL in a new tab.              |

### General

| `name`   | `args` | Effect                                                                                      |
|----------|--------|---------------------------------------------------------------------------------------------|
| `cancel` | none   | Dismiss the current transient page state: clears the highlight and hides the hint overlay. Multipurpose — teardown for new transient features is added here over time. |

> Spoken "cancel" is also handled by the daemon to abort a pending high-risk confirmation; in that case it is consumed there and no `cancel` command is sent.

---

## Control Messages (extension → daemon)

Sent **extension → daemon** to control the daemon itself rather than act on a
page. Additive to v1.0: a daemon that predates a control message ignores it.

| `type`          | fields                       | Effect                                                                                                  |
|-----------------|------------------------------|---------------------------------------------------------------------------------------------------------|
| `set_listening` | `args: { "enabled": bool }`  | Resume (`true`) or pause (`false`) the speech pipeline. Pausing **releases the microphone**; STT/VAD models stay loaded so resuming is fast. |
| `exit_input_mode` | none                       | Leave dictation (input) mode now, e.g. from the Numpad "+" hotkey. Idempotent — a no-op if not in input mode. The daemon replies `ack` and emits an `input_mode` `end` status. |

The daemon replies with `ack` carrying the same `id`. Toggling is idempotent —
resuming while already listening (or pausing while already paused) is a no-op.

```json
{
  "type": "set_listening",
  "id": "1718712000000",
  "args": { "enabled": false }
}
```

---

## Status Messages (daemon → extension)

Sent **daemon → extension** to report daemon state that the extension reflects in
its UI. Additive to v1.0: an extension that predates one ignores it. No `ack` is expected.

| `type`       | fields                      | Effect                                                                                                                                  |
|--------------|-----------------------------|----------------------------------------------------------------------------------------------------------------------------------------|
| `input_mode` | `state: "start" \| "end"`   | The daemon entered (`start`) or left (`end`) dictation mode. The extension shows/hides its input-mode indicator. Fires on entry, on "end input", and on the silence timeout. |

```json
{
  "type": "input_mode",
  "id": "1718712000000",
  "state": "start"
}
```

---

## Response Messages

### `ready` (extension → daemon)

Sent immediately after the extension connects.

```json
{
  "type": "ready",
  "id": "0",
  "meta": {
    "version": "1.0",
    "browser": "Firefox",
    "platform": "linux"
  }
}
```

### `ack` (extension → daemon)

Acknowledges a command was received and executed.

```json
{
  "type": "ack",
  "id": "<command id>",
  "meta": { "ok": true }
}
```

### `error` (extension → daemon)

```json
{
  "type": "error",
  "id": "<command id>",
  "meta": {
    "code": "UNKNOWN_COMMAND",
    "message": "Unknown command: foo"
  }
}
```

Defined error codes:

| Code                | Meaning                                                  |
|---------------------|----------------------------------------------------------|
| `UNKNOWN_COMMAND`   | `name` not in the command reference.                     |
| `INVALID_ARGS`      | A required argument was missing or malformed.            |
| `TEXT_NOT_FOUND`    | `highlight_text` matched no visible element.             |
| `NO_ACTIVE_TARGET`  | `click` called with no highlighted target.               |
| `NO_EDITABLE_TARGET`| `input_text` called with no editable element focused.    |
| `EXECUTION_FAILED`  | The command was valid but the browser action failed.     |

### `ping` (bidirectional)

```json
{ "type": "ping", "id": "abc" }
```

The receiver replies with `ack` carrying the same `id`.

---

## Metadata

The optional `meta` object on any message may carry diagnostic context. The daemon typically attaches:

- `confidence` *(float, 0.0–1.0)* — STT confidence for the parsed transcript.
- `raw` *(string)* — the original transcript text.
- `timestamp` *(ISO-8601 string)* — when the daemon emitted the command.

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
    "timestamp": "2026-04-29T10:30:00Z"
  }
}
```

---

## Behavioral Guarantees

1. **Active target.** All commands act on the currently active tab in the focused window.
2. **Sequential execution.** The extension processes commands in receipt order; no parallelism.
3. **Hint code normalization.** Hint codes are case-insensitive and whitespace-stripped. The daemon should send canonical uppercase (`"AF"`); the extension also accepts `"af"` and `"a f"`.
4. **Transient overlays auto-dismiss.** The hint/link overlay hides on: explicit `hints_hide` or `cancel`, and navigation/URL change. The `highlight_text` target clears on: explicit `clear_highlights` or `cancel`, navigation/URL change, a new `highlight_text`, and after a successful `click`. **Both** also clear on any viewport-moving command (`scroll_*`, `page_*`, `jump_*`), since the fixed overlays would otherwise drift onto arbitrary elements.
5. **Focus restoration.** After `focus_address`, `scroll_*` commands may not affect the page until `focus_page` is sent.
6. **Silent no-ops.** Some commands have no effect but are not errors (e.g., `nav_back` with no history, `scroll_down` at end of page). The extension still returns `ack`.

---

## Safety

The MVP enforces conservative behavior:

- No automatic form submission.
- No inferred clicks — `click` acts only on a target the user explicitly named via `highlight_text`.
- `tab_close` is exposed but should be gated by the daemon's parser (e.g., disabled, or requiring a confirmation phrase) to prevent accidental data loss from misrecognition.

---

## Stability

This protocol is **stable** as of v1.0. Future revisions must be **additive**:

- New commands or new optional fields are allowed.
- Renaming or removing existing commands or required fields is not allowed.
- A breaking change requires a `version` field in the envelope and coordinated daemon + extension updates.

---

## Example End-to-End Flow

1. User holds push-to-talk and says "scroll down".
2. Daemon transcribes via Vosk, normalizes to `scroll down`, parses to `scroll_down`, and emits:
   ```json
   {
     "type": "command",
     "id": "123",
     "name": "scroll_down",
     "args": {},
     "meta": { "confidence": 0.92, "raw": "scroll down" }
   }
   ```
3. Extension receives via Native Messaging, forwards to the active tab's content script, scrolls, and replies:
   ```json
   { "type": "ack", "id": "123", "meta": { "ok": true } }
   ```

---

End of Protocol Specification v1.0.
