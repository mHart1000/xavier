/**
 * Xavier Voice Browser Control - Content Script
 *
 * Responsibilities:
 * - Execute page-level actions (scroll, jump)
 * - Render hint overlays for clickable elements
 * - Handle hint-based clicking
 * - Communicate with background script
 *
 * This script may be injected both declaratively (manifest content_scripts)
 * and programmatically (background.js on-demand injection). The load guard
 * below makes a second injection a no-op so we never register two listeners
 * or hit a const-redeclaration error.
 */

if (window.__xavierContentLoaded) {
  console.log("[Xavier Content] Already loaded; skipping re-init")
} else {
  window.__xavierContentLoaded = true

  const XAVIER_HINT_CONTAINER_ID = "xavier-hint-overlay"
  const XAVIER_HINT_CLASS = "xavier-hint"
  const DEFAULT_SCROLL_AMOUNT = 200

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
          scrollUp(args)
          break

        case "scroll_down":
          scrollDown(args)
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

        case "hints_show":
          showHints()
          break

        case "hints_hide":
          hideHints()
          break

        case "hint_click":
          hintClick(args)
          break

        case "focus_page":
          focusPage()
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
  function scrollUp(args) {
    const amount = (args && Number.isFinite(args.amount)) ? args.amount : DEFAULT_SCROLL_AMOUNT
    window.scrollBy({ top: -amount, behavior: "smooth" })
  }

  function scrollDown(args) {
    const amount = (args && Number.isFinite(args.amount)) ? args.amount : DEFAULT_SCROLL_AMOUNT
    window.scrollBy({ top: amount, behavior: "smooth" })
  }

  function pageUp() {
    window.scrollBy({ top: -window.innerHeight * 0.9, behavior: "smooth" })
  }

  function pageDown() {
    window.scrollBy({ top: window.innerHeight * 0.9, behavior: "smooth" })
  }

  function focusPage() {
    window.focus()
    if (document.activeElement && document.activeElement.blur) {
      document.activeElement.blur()
    }
    document.body.focus()
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
   * Click element by hint code
   */
  function hintClick(args) {
    const code = args && args.code

    if (!code) {
      throw new Error("Missing required argument: code")
    }

    if (hintMap.size === 0) {
      throw new Error("Cannot click hint when hints are not showing")
    }

    const normalized = String(code).toLowerCase().replace(/\s+/g, '')
    const element = hintMap.get(normalized)

    if (!element) {
      throw new Error(`Hint code not found: ${code}`)
    }

    console.log(`[Xavier Content] Clicking hint: ${code}`)

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

  console.log("[Xavier Content] Content script loaded")
}
