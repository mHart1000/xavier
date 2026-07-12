/**
 * Xavier Voice Browser Control - Background Script
 * 
 * Responsibilities:
 * - Connect to native messaging host (daemon)
 * - Route commands from daemon to appropriate handlers
 * - Execute browser-level actions (tabs, navigation)
 * - Forward page-level actions to content scripts
 */

const NATIVE_HOST_NAME = "com.xavier.voice_browser"

let nativePort = null

// Gates per-message logging; errors and warnings always log.
const DEBUG = false

// Reconnect backoff: doubles while the daemon is unreachable (capped), resets
// once a message arrives; the popup can force an instant retry.
const RECONNECT_BASE_MS = 3000
const RECONNECT_MAX_MS = 60000
let reconnectDelay = RECONNECT_BASE_MS
let reconnectTimer = null

// Desired daemon state: "listening" | "deafened" | "off". In-memory for the
// session; the open native port keeps this background script alive, and we
// re-assert it on every (re)connect so a deafen/off choice survives a daemon
// restart (which defaults on). Voice toggles arrive as listening_state events.
let listenState = "listening"
const LISTEN_STATES = ["listening", "deafened", "off"]

// Whether the daemon is in dictation mode; combined with listenState for the badge.
let inputModeActive = false

/**
 * Initialize native messaging connection
 */
function connectNativeHost() {
  console.log("[Xavier] Connecting to native host:", NATIVE_HOST_NAME)
  
  try {
    nativePort = browser.runtime.connectNative(NATIVE_HOST_NAME)

    nativePort.onMessage.addListener(handleNativeMessage)

    nativePort.onDisconnect.addListener(() => {
      console.error("[Xavier] Native host disconnected:", browser.runtime.lastError)
      nativePort = null

      // Let an open popup show "Daemon not connected".
      browser.runtime.sendMessage({ type: "listening_state_changed", state: listeningState() })
        .catch(() => {})  // no popup open

      scheduleReconnect()
    })

    console.log("[Xavier] Connected to native host")

    sendReady()
    pushListeningState()
  } catch (error) {
    console.error("[Xavier] Failed to connect to native host:", error)
    scheduleReconnect()
  }
}

function scheduleReconnect() {
  reconnectTimer = setTimeout(connectNativeHost, reconnectDelay)
  reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS)
}

/**
 * Popup interaction while disconnected: skip the pending backoff and retry now.
 */
function retryConnectNow() {
  if (nativePort !== null) return
  clearTimeout(reconnectTimer)
  reconnectTimer = null
  reconnectDelay = RECONNECT_BASE_MS
  connectNativeHost()
}

/**
 * Handle incoming messages from native host
 */
function handleNativeMessage(message) {
  reconnectDelay = RECONNECT_BASE_MS  // daemon proven alive
  if (DEBUG) console.log("[Xavier] Received message:", message)
  
  if (!message || !message.type) {
    console.error("[Xavier] Invalid message format:", message)
    return
  }
  
  switch (message.type) {
    case "command":
      handleCommand(message)
      break

    case "ping":
      sendAck(message.id)
      break

    case "input_mode":
      handleInputMode(message)
      break

    case "confirm":
      handleConfirmPrompt(message)
      break

    case "listening_state":
      handleListeningState(message)
      break

    default:
      console.warn("[Xavier] Unknown message type:", message.type)
  }
}

/**
 * Daemon entered/left dictation mode: update the toolbar badge and on-page indicator.
 */
function handleInputMode(message) {
  const active = message.state === "start"
  inputModeActive = active
  renderBadge()
  showInputIndicator(active).catch(error =>
    console.error("[Xavier] input indicator toggle failed:", error)
  )
}

/**
 * Daemon listening state changed (voice or popup initiated). Store it, update
 * the badge, and let an open popup re-render.
 */
function handleListeningState(message) {
  if (!LISTEN_STATES.includes(message.state)) return
  listenState = message.state
  renderBadge()
  browser.runtime.sendMessage({ type: "listening_state_changed", state: listeningState() })
    .catch(() => {})  // no popup open
  if (message.state === "deafened" || message.state === "listening") {
    flashListeningStateInTab(message.state)
  }
}

function flashListeningStateInTab(state) {
  browser.tabs.query({ active: true, currentWindow: true }).then(tabs => {
    if (!tabs[0]) return
    browser.tabs.sendMessage(tabs[0].id, {
      command: "listening_state_flash",
      args: { state }
    }).catch(() => {})  // tab may not have the content script; that's fine
  })
}

/**
 * Toolbar badge derived from both flags, so event order doesn't matter:
 * input mode wins, then deafened, else clear.
 */
function renderBadge() {
  if (inputModeActive) {
    browser.action.setBadgeText({ text: "●" })
    browser.action.setBadgeBackgroundColor({ color: "#ff6b00" })
  } else if (listenState === "deafened") {
    browser.action.setBadgeText({ text: "–" })
    browser.action.setBadgeBackgroundColor({ color: "#6b6b6b" })
  } else if (listenState === "off") {
    browser.action.setBadgeText({ text: "–" })
    browser.action.setBadgeBackgroundColor({ color: "#000000" })
  } else {
    browser.action.setBadgeText({ text: "" })
  }
}

/**
 * Show/hide the on-page input-mode indicator in the active tab.
 */
async function showInputIndicator(active) {
  const tabs = await browser.tabs.query({ active: true, currentWindow: true })
  if (!tabs[0]) return

  const tab = tabs[0]
  const message = { command: active ? "input_mode_on" : "input_mode_off", args: {} }

  try {
    await browser.tabs.sendMessage(tab.id, message)
  } catch (error) {
    // Inject and retry when showing; on hide a missing script means nothing to clear.
    if (active && isNoReceiverError(error)) {
      await injectContentScript(tab)
      await browser.tabs.sendMessage(tab.id, message)
    }
  }
}

// Tab that currently shows the high-risk confirm prompt, so we can clear it there
// even after the confirmed action switches the active tab (open_url opens a new one).
let confirmPromptTabId = null

/**
 * Daemon is awaiting / done awaiting a spoken "confirm" for a high-risk command.
 */
function handleConfirmPrompt(message) {
  showConfirmPrompt(message.state === "start", message.command).catch(error =>
    console.error("[Xavier] confirm prompt toggle failed:", error)
  )
}

/**
 * Show/hide the on-page confirmation prompt. On show it targets the active tab and
 * remembers it; on hide it clears that same tab (which may already be gone).
 */
async function showConfirmPrompt(active, command) {
  if (active) {
    const tabs = await browser.tabs.query({ active: true, currentWindow: true })
    if (!tabs[0]) return

    const tab = tabs[0]
    confirmPromptTabId = tab.id
    const message = { command: "confirm_prompt_on", args: { command } }
    try {
      await browser.tabs.sendMessage(tab.id, message)
    } catch (error) {
      if (isNoReceiverError(error)) {
        await injectContentScript(tab)
        await browser.tabs.sendMessage(tab.id, message)
      }
    }
    return
  }

  if (confirmPromptTabId == null) return
  const tabId = confirmPromptTabId
  confirmPromptTabId = null
  // Tab may be gone (tab_close confirmed) — a failed send just means nothing to clear.
  browser.tabs.sendMessage(tabId, { command: "confirm_prompt_off", args: {} }).catch(() => {})
}

/**
 * Route command to appropriate handler
 */
async function handleCommand(message) {
  const { id, name, args } = message
  
  if (DEBUG) console.log(`[Xavier] Executing command: ${name}`, args)
  
  try {
    switch (name) {
      case "nav_back":
        await executeBack()
        break

      case "nav_forward":
        await executeForward()
        break

      case "nav_reload":
        await executeReload()
        break

      case "tab_new":
        await executeNewTab()
        break

      case "tab_close":
        await executeCloseTab()
        break

      case "tab_next":
        await executeNextTab()
        break

      case "tab_prev":
        await executePrevTab()
        break

      case "focus_address":
        await executeFocusAddress()
        break

      case "open_url":
        await executeOpenUrl(args)
        break

      case "scroll_up":
      case "scroll_down":
      case "page_up":
      case "page_down":
      case "jump_top":
      case "jump_bottom":
      case "hints_show":
      case "hints_hide":
      case "links_show":
      case "link_select":
      case "highlight_text":
      case "highlight_next":
      case "highlight_previous":
      case "click":
      case "open_new_tab":
      case "clear_highlights":
      case "cancel":
      case "focus_page":
      case "input_text":
        await forwardToContentScript(name, args)
        break

      default:
        sendError(id, "UNKNOWN_COMMAND", `Unknown command: ${name}`)
        return
    }

    sendAck(id)
  } catch (error) {
    console.error(`[Xavier] Command failed: ${name}`, error)
    sendError(id, "EXECUTION_FAILED", error.message)
  }
}

/**
 * Navigation Actions
 */
async function executeBack() {
  const tabs = await browser.tabs.query({ active: true, currentWindow: true })
  if (tabs[0]) {
    await browser.tabs.goBack(tabs[0].id)
  }
}

async function executeForward() {
  const tabs = await browser.tabs.query({ active: true, currentWindow: true })
  if (tabs[0]) {
    await browser.tabs.goForward(tabs[0].id)
  }
}

async function executeReload() {
  const tabs = await browser.tabs.query({ active: true, currentWindow: true })
  if (tabs[0]) {
    await browser.tabs.reload(tabs[0].id)
  }
}

/**
 * Tab Actions
 */
async function executeNewTab() {
  await browser.tabs.create({})
}

async function executeCloseTab() {
  const tabs = await browser.tabs.query({ active: true, currentWindow: true })
  if (tabs[0]) {
    await browser.tabs.remove(tabs[0].id)
  }
}

async function executeNextTab() {
  const tabs = await browser.tabs.query({ currentWindow: true })
  const active = tabs.find(t => t.active)
  
  if (active) {
    const currentIndex = tabs.indexOf(active)
    const nextIndex = (currentIndex + 1) % tabs.length
    await browser.tabs.update(tabs[nextIndex].id, { active: true })
  }
}

async function executePrevTab() {
  const tabs = await browser.tabs.query({ currentWindow: true })
  const active = tabs.find(t => t.active)
  
  if (active) {
    const currentIndex = tabs.indexOf(active)
    const prevIndex = (currentIndex - 1 + tabs.length) % tabs.length
    await browser.tabs.update(tabs[prevIndex].id, { active: true })
  }
}

/**
 * Address Bar Actions
 */
async function executeFocusAddress() {
  // Note: This requires user interaction in Firefox
  // May not work reliably in all contexts
  console.log("[Xavier] Focus address bar requested (may require user interaction)")
}

async function executeOpenUrl(args) {
  const url = args?.url
  if (!url) {
    throw new Error("URL not provided")
  }
  
  await browser.tabs.create({ url })
}

/**
 * Forward command to content script in active tab
 */
async function forwardToContentScript(commandName, args) {
  const tabs = await browser.tabs.query({ active: true, currentWindow: true })

  if (!tabs[0]) {
    throw new Error("No active tab found")
  }

  const tab = tabs[0]
  const message = { command: commandName, args: args || {} }

  let response
  try {
    response = await browser.tabs.sendMessage(tab.id, message)
  } catch (error) {
    // No content script in the tab yet (tab predates the extension, or the
    // extension was reloaded and orphaned the old script). Inject and retry once.
    if (isNoReceiverError(error)) {
      await injectContentScript(tab)
      response = await browser.tabs.sendMessage(tab.id, message)
    } else {
      console.error("[Xavier] Failed to forward to content script:", error)
      throw new Error(`Content script not ready: ${error.message}`)
    }
  }

  if (response && response.error) {
    throw new Error(response.error)
  }
}

/**
 * True when sendMessage failed because no content script was listening.
 */
function isNoReceiverError(error) {
  const text = (error && error.message) || ""
  return /receiving end does not exist|could not establish connection/i.test(text)
}

/**
 * Programmatically inject the content script into a tab. Fails on privileged
 * pages (about:, view-source:, moz-extension:) where injection is forbidden.
 */
async function injectContentScript(tab) {
  if (!tab.url || /^(about:|view-source:|moz-extension:|chrome:|resource:)/.test(tab.url)) {
    throw new Error(`Cannot run on this page: ${tab.url || "unknown"}`)
  }

  console.log("[Xavier] Injecting content script into tab", tab.id)
  await browser.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["content/content.js"]
  })
}

/**
 * Tell the daemon the desired listening state. Idempotent on the daemon side,
 * so it is safe to re-assert after every connect. `enabled` kept for protocol
 * compatibility with daemons that predate the tri-state.
 */
function pushListeningState() {
  if (!nativePort) return

  nativePort.postMessage({
    type: "set_listening",
    id: String(Date.now()),
    args: { state: listenState, enabled: listenState !== "off" }
  })
}

function sendReady() {
  if (!nativePort) return

  nativePort.postMessage({
    type: "ready",
    id: "0",
    meta: {
      version: "1.0",
      browser: "Firefox",
      platform: navigator.platform || "unknown"
    }
  })
}

function sendAck(id) {
  if (!nativePort) {
    console.error("[Xavier] Cannot send ack: no native connection")
    return
  }

  nativePort.postMessage({
    type: "ack",
    id: id,
    meta: { ok: true }
  })
}

function sendError(id, code, message) {
  if (!nativePort) {
    console.error("[Xavier] Cannot send error: no native connection")
    return
  }

  nativePort.postMessage({
    type: "error",
    id: id,
    meta: { code: code, message: message }
  })
}

/**
 * Runtime messages from the rest of the extension:
 * - content scripts ask to open a link in a new background tab (the ctrl-click
 *   equivalent: new tab, focus stays put). The content script owns which
 *   element is highlighted; the background owns tabs.
 * - the popup reads and toggles the listening state.
 * State queries return a Promise so the popup receives the reply.
 */
browser.runtime.onMessage.addListener((message, sender) => {
  if (!message) return

  if (message.type === "open_tab") {
    browser.tabs.create({
      url: message.url,
      active: false,
      openerTabId: sender.tab && sender.tab.id
    }).catch(error => console.error("[Xavier] open_tab failed:", error))
    return
  }

  if (message.type === "get_listening_state") {
    retryConnectNow()
    return Promise.resolve(listeningState())
  }

  if (message.type === "set_listening") {
    retryConnectNow()
    if (LISTEN_STATES.includes(message.state)) {
      listenState = message.state
      renderBadge()
      pushListeningState()
    }
    return Promise.resolve(listeningState())
  }

  if (message.type === "exit_input_mode") {
    if (nativePort) {
      nativePort.postMessage({ type: "exit_input_mode", id: String(Date.now()) })
    }
    return
  }
})

function listeningState() {
  return { state: listenState, connected: nativePort !== null }
}

// Initialize on startup
connectNativeHost()

console.log("[Xavier] Background script loaded")
