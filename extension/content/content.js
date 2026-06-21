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
  const XAVIER_INPUT_INDICATOR_ID = "xavier-input-indicator"
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

  // Viewport-moving commands; dismiss the fixed overlays first so they don't drift.
  const VIEWPORT_MOVING_COMMANDS = new Set([
    "scroll_up", "scroll_down", "page_up", "page_down", "jump_top", "jump_bottom"
  ])

  // <input> types that accept dictated text (input mode).
  const TEXT_INPUT_TYPES = new Set([
    "text", "search", "email", "url", "password", "tel", "number"
  ])

  let hintElements = []
  let hintMap = new Map()
  let activeTarget = null
  let matchList = []
  let matchIndex = 0

  /**
   * Listen for commands from background script
   */
  browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log("[Xavier Content] Received command:", message)

    const { command, args } = message

    try {
      if (VIEWPORT_MOVING_COMMANDS.has(command)) {
        handleCancel()
      }

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

        case "open_new_tab":
          openActiveTargetInNewTab()
          break

        case "clear_highlights":
          clearHighlights()
          break

        case "cancel":
          handleCancel()
          break

        case "highlight_next":
          cycleMatch(1)
          break

        case "highlight_previous":
          cycleMatch(-1)
          break

        case "focus_page":
          focusPage()
          break

        case "input_text":
          inputText(args)
          break

        case "input_mode_on":
          showInputIndicator()
          break

        case "input_mode_off":
          hideInputIndicator()
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
   * Type dictated text into the focused editable element (input mode). Inserts at
   * the caret with execCommand("insertText"), which fires the native input events
   * that framework-controlled fields (React/Vue) listen for — a plain value
   * assignment would be ignored. Falls back to setRangeText where execCommand is
   * unavailable. Assumes the user's field is still focused; forwarding the command
   * via tabs.sendMessage does not move page focus.
   */
  function inputText(args) {
    const text = args && args.text

    if (!text) {
      throw new Error("Missing required argument: text")
    }

    const el = document.activeElement
    if (!isEditableTarget(el)) {
      throw new Error("No editable field focused")
    }

    // Space-separate successive utterances so they don't run together.
    const insert = needsLeadingSpace(el) ? " " + text : text

    el.focus()
    if (document.execCommand("insertText", false, insert)) {
      return
    }

    // Fallback: splice at the caret (input/textarea) or append (contenteditable).
    if (typeof el.setRangeText === "function" && el.selectionStart != null) {
      el.setRangeText(insert, el.selectionStart, el.selectionEnd, "end")
    } else {
      el.textContent = (el.textContent || "") + insert
    }
    el.dispatchEvent(new Event("input", { bubbles: true }))
  }

  /**
   * True for a text-bearing <input>, a <textarea>, or a contenteditable element.
   */
  function isEditableTarget(el) {
    if (!el) return false
    if (el.isContentEditable) return true

    const tag = el.tagName && el.tagName.toLowerCase()
    if (tag === "textarea") return true
    if (tag === "input") {
      // type defaults to "text"; exclude checkbox/button/etc.
      return TEXT_INPUT_TYPES.has((el.getAttribute("type") || "text").toLowerCase())
    }
    return false
  }

  /**
   * Whether to prepend a space so consecutive dictated utterances stay separated:
   * true when text precedes the caret and doesn't already end in whitespace.
   */
  function needsLeadingSpace(el) {
    if (el.isContentEditable) {
      const existing = el.textContent || ""
      return existing.length > 0 && !/\s$/.test(existing)
    }
    const caret = el.selectionStart
    if (caret == null || caret === 0) return false
    return !/\s/.test(el.value.charAt(caret - 1))
  }

  /**
   * Fixed-corner badge shown while the daemon is in input mode.
   */
  function showInputIndicator() {
    hideInputIndicator()

    const badge = document.createElement("div")
    badge.id = XAVIER_INPUT_INDICATOR_ID
    badge.textContent = '● Input mode — say "end input" to finish'
    badge.style.cssText = `
      position: fixed;
      bottom: 16px;
      right: 16px;
      background: #ff6b00;
      color: white;
      padding: 8px 14px;
      border-radius: 16px;
      font-family: system-ui, sans-serif;
      font-size: 13px;
      font-weight: bold;
      pointer-events: none;
      z-index: 2147483647;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    `
    document.body.appendChild(badge)
  }

  function hideInputIndicator() {
    const badge = document.getElementById(XAVIER_INPUT_INDICATOR_ID)
    if (badge) {
      badge.remove()
    }
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
   * Clickable elements currently in the viewport - for the hint overlay, which
   * can only label what the user can see.
   */
  function collectClickableElements() {
    const elements = document.querySelectorAll(CLICKABLE_SELECTORS.join(','))
    return Array.from(elements).filter(el => isRendered(el) && isInViewport(el))
  }

  /**
   * Clickable elements anywhere on the page (rendered, not necessarily on
   * screen) - for text matching, so "next" can step to matches below the fold
   * and scroll them into view.
   */
  function collectMatchableElements() {
    const elements = document.querySelectorAll(CLICKABLE_SELECTORS.join(','))
    return Array.from(elements).filter(isRendered)
  }

  function isRendered(el) {
    const rect = el.getBoundingClientRect()
    const style = window.getComputedStyle(el)

    return (
      rect.width > 0 &&
      rect.height > 0 &&
      style.visibility !== 'hidden' &&
      style.display !== 'none'
    )
  }

  function isInViewport(el) {
    const rect = el.getBoundingClientRect()

    return (
      rect.top < window.innerHeight &&
      rect.bottom > 0 &&
      rect.left < window.innerWidth &&
      rect.right > 0
    )
  }

  /**
   * Text/class targeting - highlight an element by its visible text or first
   * class name. All matches are kept as an ordered list (the active one is the
   * click target) so "next"/"previous" step through repeats; an optional ordinal
   * arg selects the starting match.
   */
  function highlightText(args) {
    const text = args && args.text

    if (!text) {
      throw new Error("Missing required argument: text")
    }

    // Capture the prior target as an anchor before clearing (nearest-match bias).
    const anchor = activeTarget
    clearHighlights()

    // Try the full phrase first (a real target ending in a number word wins), else text + position.
    let matches = []
    let start = 1
    if (args.literal) {
      matches = findMatches(normalizeLabel(args.literal), anchor)
    }
    if (matches.length === 0) {
      matches = findMatches(normalizeLabel(text), anchor)
      start = (args && args.ordinal) || 1
    }

    if (matches.length === 0) {
      throw new Error(`No element matching text: ${text}`)
    }

    matchList = matches
    matchIndex = Math.min(Math.max(start - 1, 0), matchList.length - 1)
    applyMatch()

    console.log(`[Xavier Content] Highlighted ${matchIndex + 1}/${matchList.length} for: ${text}`)
  }

  /**
   * Ordered match list for "highlight" + "next" cycling.
   *
   * Score (lower = better): a visible-text match (clickable set) beats an exact
   * first-class match (any rendered [class] element). The class pool reaches
   * JS-wired controls that have no clickable attribute.
   *
   * Then drop any match that contains another match, so a wrapping container
   * can't win over the specific element inside it. Order by anchor proximity (the
   * prior highlight) if set, else score then document order.
   */
  function findMatches(needle, anchor) {
    const byElement = new Map()

    // Text matches over the clickable set (scores 0-2).
    for (const el of collectMatchableElements()) {
      const score = textScore(el, needle)
      if (score !== null) {
        byElement.set(el, score)
      }
    }

    // Class matches (score 3), after text so text wins; cheap firstClassName gates isRendered.
    for (const el of document.querySelectorAll('[class]')) {
      if (!byElement.has(el) && firstClassName(el) === needle && isRendered(el)) {
        byElement.set(el, 3)
      }
    }

    let candidates = Array.from(byElement, ([el, score]) => ({ el, score }))
    candidates = candidates.filter(candidate =>
      !candidates.some(other => other.el !== candidate.el && candidate.el.contains(other.el))
    )

    if (anchor) {
      candidates.sort((a, b) =>
        domDistance(anchor, a.el) - domDistance(anchor, b.el) ||
        a.score - b.score
      )
    } else {
      candidates.sort((a, b) => a.score - b.score)
    }

    return candidates.map(candidate => candidate.el)
  }

  /**
   * Text-only score for an element's visible label: 0 exact, 1 prefix, 2
   * substring, null no match. Class matching is handled in findMatches.
   */
  function textScore(el, needle) {
    const label = normalizeLabel(elementLabel(el))
    if (label === needle) return 0
    if (label.startsWith(needle)) return 1
    if (label.includes(needle)) return 2
    return null
  }

  /**
   * First class name, normalized for speech: lowercased, "-"/"_" to spaces (so a
   * spoken "flat list" matches class "flat-list"). Empty string if no class.
   */
  function firstClassName(el) {
    const first = (el.classList && el.classList[0]) || ""
    return normalizeLabel(first.replace(/[-_]/g, " "))
  }

  /**
   * Tree distance between two elements: steps up from b to the lowest common
   * ancestor, plus that ancestor's depth above a. Infinity if unrelated.
   */
  function domDistance(a, b) {
    const depthFromA = new Map()
    let node = a
    let depth = 0
    while (node) {
      depthFromA.set(node, depth)
      node = node.parentElement
      depth++
    }

    node = b
    let steps = 0
    while (node) {
      if (depthFromA.has(node)) {
        return steps + depthFromA.get(node)
      }
      node = node.parentElement
      steps++
    }

    return Infinity
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
   * Open the active highlighted target's link in a new background tab (focus
   * stays on the current tab), then clear the highlight. Tab creation belongs to
   * the background script, so resolve the URL here and hand it off.
   */
  function openActiveTargetInNewTab() {
    if (!activeTarget) {
      throw new Error("No highlighted target to open")
    }

    const anchor = activeTarget.closest && activeTarget.closest('a[href]')
    const url = anchor ? anchor.href : null
    if (!url || url.startsWith("javascript:")) {
      throw new Error("Highlighted target has no link to open in a new tab")
    }

    browser.runtime.sendMessage({ type: "open_tab", url })
    clearHighlights()

    console.log("[Xavier Content] Opened active target in new tab")
  }

  /**
   * Step to the next (step=1) or previous (step=-1) match of the current text,
   * wrapping around, and highlight it.
   */
  function cycleMatch(step) {
    if (matchList.length === 0) {
      throw new Error("No highlighted matches to cycle")
    }

    matchIndex = (matchIndex + step + matchList.length) % matchList.length
    applyMatch()

    console.log(`[Xavier Content] Highlighted ${matchIndex + 1}/${matchList.length}`)
  }

  /**
   * Make matchList[matchIndex] the active target: scroll it into view when off
   * screen, then redraw the highlight box over it.
   */
  function applyMatch() {
    removeHighlightOverlay()
    activeTarget = matchList[matchIndex]

    if (!isInViewport(activeTarget)) {
      activeTarget.scrollIntoView({ block: "center", behavior: "instant" })
    }

    drawHighlight(activeTarget)
  }

  /**
   * Remove the highlight overlay and forget the active target and match list.
   */
  function clearHighlights() {
    removeHighlightOverlay()
    activeTarget = null
    matchList = []
    matchIndex = 0
  }

  function removeHighlightOverlay() {
    const container = document.getElementById(XAVIER_HIGHLIGHT_CONTAINER_ID)
    if (container) {
      container.remove()
    }
  }

  /**
   * Cancel - dismiss the current transient page state. Multipurpose by design:
   * each transient feature adds its teardown here as it is built.
   */
  function handleCancel() {
    clearHighlights()
    hideHints()
    hideInputIndicator()
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
