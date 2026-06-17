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

  // Commands that move the viewport. They invalidate the fixed-position highlight
  // and hint overlays (they would drift onto arbitrary elements), so transient
  // state is dismissed before they run.
  const VIEWPORT_MOVING_COMMANDS = new Set([
    "scroll_up", "scroll_down", "page_up", "page_down", "jump_top", "jump_bottom"
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

    // Capture the current target before clearing: a follow-up highlight anchors
    // to it so the nearest match is chosen instead of the global best.
    const anchor = activeTarget
    clearHighlights()

    const matches = findMatches(normalizeLabel(text), anchor)

    if (matches.length === 0) {
      throw new Error(`No element matching text: ${text}`)
    }

    matchList = matches
    // "highlight third expand" starts on the Nth match (1-based, clamped).
    const ordinal = (args && args.ordinal) || 1
    matchIndex = Math.min(Math.max(ordinal - 1, 0), matchList.length - 1)
    applyMatch()

    console.log(`[Xavier Content] Highlighted ${matchIndex + 1}/${matchList.length} for: ${text}`)
  }

  /**
   * Ordered elements matching the needle by visible text or first class name.
   *
   * Two pools merged by element (a text score outranks a class score): text
   * matching uses the clickable set; class matching scans every rendered element
   * with a class, so it reaches JS-wired controls with no clickable attribute
   * (e.g. Reddit's <a class="expando-button"> with no href) that the clickable
   * selectors miss.
   *
   * Keep only innermost matches - drop any candidate that contains another
   * candidate. A container and an element nested inside it can both match; if the
   * container is allowed to win it becomes the target, and proximity measured
   * from a container favors sibling containers over its own descendants, so a
   * later anchored highlight resolves to the wrong group. Restricting to
   * innermost matches keeps the target specific.
   *
   * Order: with an anchor (the previously highlighted element), nearest in the
   * DOM tree first. Without one, by match score; ties keep document order (stable
   * sort), so "next" steps top to bottom down the page.
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

    // Class matches over any rendered element whose first class equals the needle
    // (score 3). Checked after text so a text match wins; firstClassName (cheap)
    // gates the layout-reading isRendered.
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
