
---

# **Voice-Controlled Browser Assistant — Project Summary**

## **Project Goal**

Create a **fully open-source, privacy-first voice control system for Firefox**, starting with Windows support but designed from the beginning to be cross-platform. The system will enable voice-driven browsing using **offline speech recognition** and a **custom Firefox extension** communicating through **Native Messaging**.

The long-term goal is a polished, user-friendly package.
The MVP goal is **functional and reliable voice navigation with a small command set**.

The working name of the project is  Xavier.
---

# **High-Level Architecture**

## **1. Local Voice Daemon (Python MVP → Rust later)**

A desktop application that:

* Captures microphone audio
* Performs **offline speech-to-text** (STT) using **Vosk** (Whisper later as an option)
* Parses transcripts into structured command objects
* Communicates with the browser extension via **Native Messaging (stdio JSON framing)**
* Provides push-to-talk UX in early versions
* Never sends audio or transcripts to the cloud

This component must remain **modular** so the Python implementation can be replaced by Rust later without affecting the extension or protocol.

### Daemon Responsibilities

* Audio capture (sounddevice)
* STT (vosk)
* Intent parsing → structured JSON commands
* Send commands to extension
* Logging and local config ONLY
* Explicitly **no DOM logic**, no automation heuristics

---

## **2. Firefox WebExtension**

A Manifest V3 extension that:

* Connects to the local daemon using Firefox Native Messaging
* Executes browser actions:

  * tab management
  * history navigation
  * scrolling and jumping
  * hint overlays + clicking page elements
  * optional URL-opening
* Injects a content script into all pages
* Draws and manages hint overlays
* Ensures a conservative, predictable, safe interaction model

The extension is responsible for all **browser- and page-level effects**, keeping the daemon side simple and platform-agnostic.

### Extension Responsibilities

* json → browser action routing
* hint overlay rendering and destruction
* clicking elements by label
* scroll / jump commands
* tab + navigation commands
* reporting errors (optional in MVP)

Extension must never attempt its own STT or audio capture.

---

## **3. Communication Layer: Native Messaging**

The daemon ↔ extension bridge is **Firefox Native Messaging**, using:

* Stdin/stdout
* 4-byte little-endian length prefix
* JSON payload

This avoids networking, avoids servers, avoids privacy risk, and works cross-platform.

### Envelope Schema (stable contract)

All messages follow:

```json
{
  "type": "command",
  "id": "uuid-or-int",
  "name": "...",
  "args": { ... },
  "meta": { "confidence": 0.xx, "raw": "..." }
}
```

Supported `type`s: `command`, `ack`, `error`, `ping` (small set).

This schema **must remain stable** to support multi-language daemons in the future.

---

# **MVP Feature Set**

The MVP focuses on a minimal but powerful set of commands:

## **Navigation**

* back
* forward
* reload

## **Scrolling**

* scroll up / scroll down
* page up / page down
* jump top / jump bottom

## **Tabs**

* new tab
* close tab (confirmation or disabled in MVP)
* next tab
* previous tab

## **Hint-Based Clicking**

* show hints (render overlay of labeled clickable elements)
* hide hints
* click <hint> (interprets AF, B7, etc.)

Hints enable general page interaction without AI heuristics.

## **Address Bar (optional MVP)**

* focus address
* open url <x>

---

# **Command Grammar (Speech → Intent)**

Transcripts are normalized:

* lowercase
* remove punctuation
* collapse whitespace

Synonyms map to canonical commands:

* “go back” → back
* “scroll down”, “down” → scroll_down
* “click A F”, “click AF” → hint_click("AF")

Intent parser must be deterministic and predictable.

Hint parsing must accept:

* “click AF”
* “click a f”
* “click a f f” → normalize to “AFF” (later)

---

# **Constraints and Non-Goals for MVP**

1. **Push-to-talk only**

   * No always-listening
   * No wake word
   * No background hotkeys (initially)

2. **Privacy-first**

   * Audio stays local
   * No cloud APIs
   * No telemetry

3. **DOM safety**

   * No automatic form submissions
   * No inferential “click submit” logic
   * No destructive operations without explicit commands

4. **Simple installation** (Windows first)

   * Python venv
   * Registry-based native host registration
   * Manual extension load

5. **Codebase must preserve future Rust migration possibility**

   * All interfaces defined by the protocol
   * Python implementation must stay modular

---

# **Technologies Used**

## **Daemon / Backend**

* **Python 3.11+**
* **Vosk** for offline STT
* **sounddevice** for cross-platform mic access
* **JSON** for messages
* **Native Messaging** for communication
* **Windows** as primary dev target
* Later: **Rust reimplementation** for speed, packaging, cross-platform binary distribution

## **Browser Extension**

* Firefox WebExtension (Manifest V3)
* `browser.runtime.connectNative`
* `browser.tabs.*` API
* `browser.scripting.executeScript`
* Content scripts
* DOM manipulation for hints

## **Development Environment**

* Windows as primary OS
* Cross-platform support considered from day one
* No platform-specific hotkeys or wake-word logic in MVP

---

# **Repository Structure**

```
voice-browser-mvp/
  extension/
    manifest.json
    background/
      background.js
    content/
      content.js
  daemon/
    main.py
    config.json
    models/
      vosk-en/
    core/
      parser.py
      stt_interface.py
    native_messaging/
      framing.py
    platform/
      windows.py
      linux.py (stub)
      macos.py (stub)
  protocol/
    protocol.md
  install/
    register_native_host.ps1
    voice-browser-daemon.bat
```

---

# **Development Roadmap (MVP → beyond)**

## **MVP Phase (must finish before anything else)**

1. Build extension skeleton
2. Build daemon skeleton
3. Implement native messaging handshake
4. Establish JSON protocol contract
5. Implement hint overlay + click
6. Implement scroll, nav, tab actions
7. Add Vosk transcription
8. Add transcript → command parser
9. End-to-end smoke test

## **Post-MVP Phase**

1. Better push-to-talk UX
2. Optional “confidence confirmation” for risky commands
3. Config UI (later, maybe via extension)
4. Replace Python daemon with Rust version
5. macOS + Linux installers
6. Add wake-word mode (optional, far later)
7. Add Whisper support (optional)

---

# **Success Criteria for MVP**

The MVP is considered complete when all of the following occur:

* The daemon and extension connect correctly on Windows
* User can:

  * Press Enter
  * Speak a command
  * See hints, scroll pages, navigate tabs, click elements
* No cloud services are involved
* Audio is kept local
* JSON protocol remains stable
* System operates with predictable latency (target <300ms command → action)
* No destructive commands run without explicit user intention

---

# **Guiding Principles for the Project**

1. **Privacy-first**

   * No cloud STT
   * No telemetry
   * Local-only processing

2. **Predictability over cleverness**

   * Deterministic grammar-based commands
   * No “AI guessing” what the user meant

3. **Safety-conscious design**

   * No silent destructive actions
   * No form submissions
   * No automatic clicks except explicitly selected hints

4. **Modularity**

   * Daemon swappable (Python → Rust)
   * STT engines swappable (Vosk → Whisper)
   * Protocol stable and documented

5. **Cross-platform readiness**

   * Avoid OS-specific shortcuts early
   * Introduce hotkeys, tray icons, installers later

---

# **How an Agent Should Use This Summary**

Any agent or GPT workspace using this summary should:

* Preserve the architecture (daemon ↔ protocol ↔ extension)
* Never recommend cloud STT or privacy-compromising approaches
* Avoid adding scope (e.g., wake word, global hotkeys) until MVP complete
* Keep commands deterministic and grammar-based
* Maintain the JSON protocol stability
* Keep daemon & extension responsibilities separate
* Prioritize Windows but keep Linux/macOS in mind
* Assume user values privacy, openness, and correctness over shortcuts
* Consider future Rust migration in all design recommendations

---

# **Agent Execution Plan — Step-By-Step Instructions**

This plan is broken into **major phases**, each with **explicit steps**, **goals**, **success conditions**, and **what NOT to do**.

The agent should **not advance to the next phase** until all success conditions of the current phase are clearly met.

---

# **PHASE 0 — Initialization**

### **Step 0.1 — Adopt required project constraints**

The agent must internalize and enforce:

* Privacy-first
* Offline STT only
* No cloud APIs
* No destructive automation
* No wake-word, no always-listening (MVP only)
* No global hotkeys (MVP only)
* Daemon/Extension responsibilities must not bleed
* Stable JSON protocol
* Upgradable architecture (Python → Rust)

### **Step 0.2 — Adopt the architecture model**

Agent must recognize:

* **Daemon** = audio → STT → intent → JSON command
* **Extension** = execute browser actions
* **Native Messaging** as IPC

### **Phase 0 Success Conditions**

* The agent acknowledges the architecture
* The agent acknowledges constraints
* The agent will reject any suggestion violating privacy or MVP rules

---

# **PHASE 1 — Protocol Definition**

### **Step 1.1 — Define the JSON envelope**

Agent must produce and maintain the `protocol.md` with:

```
{
  "type": "command",
  "id": "uuid-or-int",
  "name": "command_name",
  "args": { ... },
  "meta": { ... }
}
```

### **Step 1.2 — Define allowed command names**

Agent ensures the full MVP list exists:

* nav: back / forward / reload
* scroll: up / down / page up / page down
* jump: top / bottom
* tabs: new / close / next / prev
* hints: show / hide / hint_click
* focus: address (optional for MVP)
* open_url (optional for MVP)

### **Step 1.3 — Define error + ack messages**

Agent must include:

* `{type: "ack", id: …, ok: true}`
* `{type: "error", id: …, message: "..."}`

### **Phase 1 Success Conditions**

* Protocol is documented
* Protocol is stable
* No command ambiguity exists
* Daemon and extension share identical protocol definitions

---

# **PHASE 2 — Firefox Extension Skeleton**

### **Step 2.1 — Create extension folder structure**

* manifest.json
* background script
* content script

### **Step 2.2 — Create manifest.json**

Agent must include:

* `"permissions": ["nativeMessaging", "tabs", "scripting", "activeTab"]`
* `"browser_specific_settings.gecko.id": "voice-browser-mvp@local"`
* content script injection on all pages

### **Step 2.3 — Create background.js skeleton**

Must include:

* Native Messaging connect
* Message routing (switch on command name)
* Forwarding scroll/jump/hints/hint_click to content script
* Tab + nav handling internally

### **Step 2.4 — Create content.js skeleton**

Must include empty handlers for:

* scroll
* jump
* hints show/hide
* hint_click

### **Phase 2 Success Conditions**

* Extension loads in `about:debugging`
* Background + content scripts run
* No functionality required yet — structure only

---

# **PHASE 3 — Daemon Skeleton (Python)**

### **Step 3.1 — Create Python structure**

* main.py
* core/parser.py
* native_messaging/framing.py
* platform/windows.py
* config.json

### **Step 3.2 — Implement Native Messaging framing**

Agent must implement:

* read_message()
* send_message()
* proper little-endian length handling

### **Step 3.3 — Implement main loop stub**

For now:

* Print READY
* Hardcode sending a static test command on Enter press

### **Phase 3 Success Conditions**

* Daemon runs with no errors
* Daemon can send a hardcoded command
* Agent confirms ready for native messaging hookup

---

# **PHASE 4 — Native Messaging Integration (Windows)**

### **Step 4.1 — Create host manifest**

Agent creates:

* `com.matt.voice_browser` manifest
* correct `"path"` to launcher
* correct `"allowed_extensions"`

### **Step 4.2 — Create launcher .bat file**

Must:

* activate the venv
* call python main.py
* use absolute paths

### **Step 4.3 — Create PowerShell installer**

Registers host manifest under:

```
HKCU\Software\Mozilla\NativeMessagingHosts\com.matt.voice_browser
```

### **Step 4.4 — Perform handshake test**

Steps:

1. Load extension
2. Start daemon
3. Background connects to daemon
4. Daemon prints handshake
5. Daemon sends `{command: "nav", back}`
6. Browser must go back

### **Phase 4 Success Conditions**

* Extension ↔ daemon communication works
* Commands can be passed and executed manually
* No STT yet

---

# **PHASE 5 — Implement Browser Actions**

### **Step 5.1 — Background script**

Agent must implement:

* Tab actions (new/close/next/prev)
* Nav actions (back/forward/reload)
* Focus address (optional)
* Forwarding scroll/hints to content script

### **Step 5.2 — Content script**

Agent must implement:

* scroll (window.scrollBy)
* jump (top/bottom)
* hint overlay generator
* hint_click logic
* overlay cleanup

### **Step 5.3 — Manual command testing**

Using hardcoded daemon output:

* Show hints
* Click a hint
* Scroll
* Tab navigation

### **Phase 5 Success Conditions**

* Every MVP action works via manual test commands
* No STT yet
* System is safe, deterministic, and predictable

---

# **PHASE 6 — Add Offline STT (Vosk)**

### **Step 6.1 — Download & load model**

Agent ensures:

* Lightweight English model
* Model path stored in config.json

### **Step 6.2 — Implement audio capture**

* sounddevice
* 16 kHz mono frames

### **Step 6.3 — Integrate Vosk recognizer**

* Continuous feed of frames
* Final result → transcript

### **Step 6.4 — Replace hardcoded command with STT → command**

* Normalize transcript
* Parse using parser.py
* Emit command JSON

### **Phase 6 Success Conditions**

* User presses Enter, speaks text, receives transcript
* Commands execute in browser
* Latency is acceptable (< ~300ms average)
* No errors or crashes

---

# **PHASE 7 — Command Parser**

### **Step 7.1 — Define mapping rules**

* synonyms → canonical commands
* phrase detection
* hint code extraction

### **Step 7.2 — Implement parser in Python**

* return structured command object
* include meta (confidence, raw transcript)

### **Step 7.3 — Add safety constraints**

* disable or confirm “close tab”
* never infer clicks other than hint codes

### **Phase 7 Success Conditions**

* Speech commands map reliably
* Incorrect transcripts do NOT trigger unsafe actions
* All expected commands produce valid protocol messages

---

# **PHASE 8 — End-to-End MVP Completion**

### **Step 8.1 — Full workflow tests**

Agent must verify:

1. User presses Enter
2. Speaks a command
3. Transcript recognized
4. Command parsed
5. JSON sent to extension
6. Browser performs action

### **Step 8.2 — Commands verified**

* back
* forward
* reload
* scroll up/down
* page up/down
* jump top/bottom
* new tab
* next/previous tab
* show hints
* hint_click

### **Step 8.3 — Error handling**

* Unknown commands produce `{type:"error"}`

### **Phase 8 Success Conditions**

* System consistently performs MVP actions
* No cloud interaction
* No unsafe automation
* Protocol is stable
* Architecture is clean for future Rust migration

---

# **PHASE 9 — Post-MVP Tasks (Agent must NOT do these early)**

These are strictly forbidden during MVP but allowed only after explicit user request:

* Wake word
* Always-listening mode
* Global hotkeys
* macOS/Linux installers
* Whisper integration
* Tray icon UI
* Settings UI in browser
* Rust daemon rewrite

Agent must decline and warn if asked to implement these early.

---

# **Agent Rules & Behavioral Constraints**

1. **Never propose cloud-based STT.**
2. **Never bypass the protocol or merge daemon/extension responsibilities.**
3. **Never introduce destructive actions without explicit user confirmation.**
4. **Never exceed MVP scope unless user explicitly asks.**
5. **Always preserve cross-platform capability in design.**
6. **Always protect user privacy by default.**
7. **Always favor deterministic behavior over “AI heuristics.”**
8. **When suggesting implementation steps, follow repo structure.**
9. **Never require external services, accounts, or network calls.**
10. **Always check before advancing phases.**

---

