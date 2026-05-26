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

      // Attempt reconnection after delay
      setTimeout(connectNativeHost, 3000)
    })

    console.log("[Xavier] Connected to native host")

    sendReady()
  } catch (error) {
    console.error("[Xavier] Failed to connect to native host:", error)
  }
}

/**
 * Handle incoming messages from native host
 */
function handleNativeMessage(message) {
  console.log("[Xavier] Received message:", message)
  
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

    default:
      console.warn("[Xavier] Unknown message type:", message.type)
  }
}

/**
 * Route command to appropriate handler
 */
async function handleCommand(message) {
  const { id, name, args } = message
  
  console.log(`[Xavier] Executing command: ${name}`, args)
  
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
      case "hint_click":
      case "focus_page":
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

// Initialize on startup
connectNativeHost()

console.log("[Xavier] Background script loaded")
