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
  const XAVIER_HIGHLIGHT_CONTAINER_ID = "xavier-highlight-overlay"
  const DEFAULT_SCROLL_AMOUNT = 200

  // Elements both the hint overlay and text highlighting can target.
  const CLICKABLE_SELECTORS = [
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

  let hintElements = []
  let hintMap = new Map()
  let activeTarget = null

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

        case "highlight_text":
          highlightText(args)
          break

        case "click":
          clickActiveTarget()
          break

        case "clear_highlights":
          clearHighlights()
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

    const visibleElements = collectClickableElements()

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

  /**
   * Shared collection of visible, clickable elements in the viewport. Used by
   * both the hint overlay and text highlighting.
   */
  function collectClickableElements() {
    const elements = document.querySelectorAll(CLICKABLE_SELECTORS.join(','))
    return Array.from(elements).filter(isVisible)
  }

  function isVisible(el) {
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
  }

  /**
   * Text targeting - highlight an element by its visible text. The element is
   * remembered as the active target so a following "click" acts on it.
   */
  function highlightText(args) {
    const text = args && args.text

    if (!text) {
      throw new Error("Missing required argument: text")
    }

    clearHighlights()

    const needle = normalizeLabel(text)
    const elements = collectClickableElements()
    const match =
      elements.find(el => normalizeLabel(elementLabel(el)) === needle) ||
      elements.find(el => normalizeLabel(elementLabel(el)).includes(needle))

    if (!match) {
      throw new Error(`No element matching text: ${text}`)
    }

    activeTarget = match
    drawHighlight(match)

    console.log(`[Xavier Content] Highlighted target for: ${text}`)
  }

  /**
   * Click the active highlighted target, then clear the highlight.
   */
  function clickActiveTarget() {
    if (!activeTarget) {
      throw new Error("No highlighted target to click")
    }

    const target = activeTarget
    // Clear first so a navigation triggered by the click leaves no stale overlay.
    clearHighlights()
    target.click()

    console.log("[Xavier Content] Clicked active target")
  }

  /**
   * Remove the highlight overlay and forget the active target.
   */
  function clearHighlights() {
    const container = document.getElementById(XAVIER_HIGHLIGHT_CONTAINER_ID)
    if (container) {
      container.remove()
    }

    activeTarget = null
  }

  /**
   * Visible label of an element: text, else aria-label, else value.
   */
  function elementLabel(el) {
    const text = (el.textContent || "").trim()
    if (text) return text

    const aria = el.getAttribute("aria-label")
    if (aria) return aria

    return el.value || ""
  }

  function normalizeLabel(value) {
    return String(value).toLowerCase().replace(/\s+/g, ' ').trim()
  }

  /**
   * Draw a single highlight box over the target element. The container is fixed
   * to the viewport, so the box uses viewport coordinates (no scroll offset).
   */
  function drawHighlight(el) {
    const container = document.createElement('div')
    container.id = XAVIER_HIGHLIGHT_CONTAINER_ID
    container.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 2147483646;
    `

    const rect = el.getBoundingClientRect()
    const box = document.createElement('div')
    box.style.cssText = `
      position: absolute;
      top: ${rect.top}px;
      left: ${rect.left}px;
      width: ${rect.width}px;
      height: ${rect.height}px;
      border: 3px solid #ff6b00;
      background: rgba(255, 107, 0, 0.15);
      border-radius: 3px;
      box-shadow: 0 0 0 2px rgba(255, 107, 0, 0.4);
      pointer-events: none;
    `

    container.appendChild(box)
    document.body.appendChild(container)
  }

  console.log("[Xavier Content] Content script loaded")
}
