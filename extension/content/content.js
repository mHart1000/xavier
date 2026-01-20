/**
 * Xavier Voice Browser Control - Content Script
 * 
 * Responsibilities:
 * - Execute page-level actions (scroll, jump)
 * - Render hint overlays for clickable elements
 * - Handle hint-based clicking
 * - Communicate with background script
 */

const XAVIER_HINT_CONTAINER_ID = "xavier-hint-overlay"
const XAVIER_HINT_CLASS = "xavier-hint"

let hintElements = []
let hintMap = new Map()

/**
 * Listen for commands from background script
 */
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("[Xavier Content] Received command:", message)
  
  const { command, args } = message
  
  try {
    switch (command) {
      case "scroll_up":
        scrollUp()
        break
      
      case "scroll_down":
        scrollDown()
        break
      
      case "page_up":
        pageUp()
        break
      
      case "page_down":
        pageDown()
        break
      
      case "jump_top":
        jumpTop()
        break
      
      case "jump_bottom":
        jumpBottom()
        break
      
      case "show_hints":
        showHints()
        break
      
      case "hide_hints":
        hideHints()
        break
      
      case "hint_click":
        hintClick(args)
        break
      
      default:
        console.warn("[Xavier Content] Unknown command:", command)
        sendResponse({ error: "Unknown command" })
        return
    }
    
    sendResponse({ ok: true })
  } catch (error) {
    console.error("[Xavier Content] Command failed:", error)
    sendResponse({ error: error.message })
  }
})

/**
 * Scroll Commands
 */
function scrollUp() {
  window.scrollBy({ top: -100, behavior: "smooth" })
}

function scrollDown() {
  window.scrollBy({ top: 100, behavior: "smooth" })
}

function pageUp() {
  window.scrollBy({ top: -window.innerHeight * 0.9, behavior: "smooth" })
}

function pageDown() {
  window.scrollBy({ top: window.innerHeight * 0.9, behavior: "smooth" })
}

/**
 * Jump Commands
 */
function jumpTop() {
  window.scrollTo({ top: 0, behavior: "smooth" })
}

function jumpBottom() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" })
}

/**
 * Hint System - Show clickable element overlays
 */
function showHints() {
  console.log("[Xavier Content] Showing hints")
  
  // Clean up any existing hints first
  hideHints()
  
  // Find all clickable elements
  const clickableSelectors = [
    'a[href]',
    'button',
    'input[type="button"]',
    'input[type="submit"]',
    'input[type="reset"]',
    '[role="button"]',
    '[onclick]',
    'select',
    'textarea',
    'input[type="text"]',
    'input[type="search"]',
    'input[type="email"]',
    'input[type="password"]',
    '[tabindex]:not([tabindex="-1"])'
  ]
  
  const elements = document.querySelectorAll(clickableSelectors.join(','))
  
  // Filter to visible elements only
  const visibleElements = Array.from(elements).filter(el => {
    const rect = el.getBoundingClientRect()
    const style = window.getComputedStyle(el)
    
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      style.visibility !== 'hidden' &&
      style.display !== 'none' &&
      rect.top < window.innerHeight &&
      rect.bottom > 0 &&
      rect.left < window.innerWidth &&
      rect.right > 0
    )
  })
  
  console.log(`[Xavier Content] Found ${visibleElements.length} visible clickable elements`)
  
  // Create overlay container
  const container = document.createElement('div')
  container.id = XAVIER_HINT_CONTAINER_ID
  container.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 2147483647;
  `
  
  document.body.appendChild(container)
  
  // Generate hint labels
  hintMap.clear()
  hintElements = []
  
  visibleElements.forEach((el, index) => {
    const label = generateHintLabel(index)
    const rect = el.getBoundingClientRect()
    
    // Create hint overlay
    const hint = document.createElement('div')
    hint.className = XAVIER_HINT_CLASS
    hint.textContent = label
    hint.style.cssText = `
      position: absolute;
      top: ${rect.top + window.scrollY}px;
      left: ${rect.left + window.scrollX}px;
      background: #ff6b00;
      color: white;
      padding: 2px 6px;
      border-radius: 3px;
      font-family: monospace;
      font-size: 12px;
      font-weight: bold;
      pointer-events: none;
      z-index: 2147483647;
      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    `
    
    container.appendChild(hint)
    
    hintMap.set(label.toLowerCase(), el)
    hintElements.push(hint)
  })
  
  console.log(`[Xavier Content] Created ${hintElements.length} hint labels`)
}

/**
 * Hide hint overlays
 */
function hideHints() {
  const container = document.getElementById(XAVIER_HINT_CONTAINER_ID)
  if (container) {
    container.remove()
  }
  
  hintMap.clear()
  hintElements = []
  
  console.log("[Xavier Content] Hints hidden")
}

/**
 * Click element by hint label
 */
function hintClick(args) {
  const label = args?.label
  
  if (!label) {
    console.error("[Xavier Content] No hint label provided")
    return
  }
  
  const normalizedLabel = label.toLowerCase().replace(/\s+/g, '')
  const element = hintMap.get(normalizedLabel)
  
  if (!element) {
    console.error(`[Xavier Content] Hint not found: ${label}`)
    return
  }
  
  console.log(`[Xavier Content] Clicking hint: ${label}`)
  
  element.click()

  hideHints()
}

/**
 * Generate hint label using base-26 (A-Z, AA-ZZ, AAA-ZZZ, etc.)
 */
function generateHintLabel(index) {
  let label = ''
  let num = index
  
  do {
    label = String.fromCharCode(65 + (num % 26)) + label
    num = Math.floor(num / 26) - 1
  } while (num >= 0)
  
  return label
}

console.log("[Xavier] Content script loaded")
