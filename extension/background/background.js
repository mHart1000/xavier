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
      sendAck(message.id, "pong")
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
      // Navigation commands
      case "back":
        await executeBack()
        break
      
      case "forward":
        await executeForward()
        break
      
      case "reload":
        await executeReload()
        break
      
      // Tab commands
      case "new_tab":
        await executeNewTab()
        break
      
      case "close_tab":
        await executeCloseTab()
        break
      
      case "next_tab":
        await executeNextTab()
        break
      
      case "prev_tab":
      case "previous_tab":
        await executePrevTab()
        break
      
      // Address bar
      case "focus_address":
        await executeFocusAddress()
        break
      
      case "open_url":
        await executeOpenUrl(args)
        break
      
      // Page-level commands (forwarded to content script)
      case "scroll_up":
      case "scroll_down":
      case "page_up":
      case "page_down":
      case "jump_top":
      case "jump_bottom":
      case "show_hints":
      case "hide_hints":
      case "hint_click":
        await forwardToContentScript(name, args)
        break
      
      default:
        throw new Error(`Unknown command: ${name}`)
    }
    
    sendAck(id, true)
  } catch (error) {
    console.error(`[Xavier] Command failed: ${name}`, error)
    sendError(id, error.message)
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
  
  const tabId = tabs[0].id
  
  // Send message to content script
  try {
    await browser.tabs.sendMessage(tabId, {
      command: commandName,
      args: args || {}
    })
  } catch (error) {
    console.error("[Xavier] Failed to forward to content script:", error)
    throw new Error(`Content script not ready: ${error.message}`)
  }
}

/**
 * Send acknowledgment to native host
 */
function sendAck(id, result = true) {
  if (!nativePort) {
    console.error("[Xavier] Cannot send ack: no native connection")
    return
  }
  
  nativePort.postMessage({
    type: "ack",
    id: id,
    ok: result
  })
}

/**
 * Send error to native host
 */
function sendError(id, message) {
  if (!nativePort) {
    console.error("[Xavier] Cannot send error: no native connection")
    return
  }
  
  nativePort.postMessage({
    type: "error",
    id: id,
    message: message
  })
}

// Initialize on startup
connectNativeHost()

console.log("[Xavier] Background script loaded")
