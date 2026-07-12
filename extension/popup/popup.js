/**
 * Xavier popup - power turns voice control fully off (mic released); deafen
 * keeps the mic open but ignores everything except the wake phrase, so
 * "<wake> listen" can bring it back.
 *
 * The mic is owned by the daemon, so the buttons only talk to the background
 * script, which relays the state down the Native Messaging port.
 */

const powerBtn = document.getElementById("power")
const deafenBtn = document.getElementById("deafen")
const statusEl = document.getElementById("status")

let current = { state: "listening", connected: false }

function render(state) {
  current = state
  const on = state.state !== "off"
  powerBtn.classList.toggle("on", on)
  powerBtn.setAttribute("aria-pressed", String(on))

  const deafened = state.state === "deafened"
  deafenBtn.classList.toggle("active", deafened)
  deafenBtn.setAttribute("aria-pressed", String(deafened))
  deafenBtn.disabled = !on || !state.connected

  if (!state.connected) {
    statusEl.textContent = "Daemon not connected"
  } else if (!on) {
    statusEl.textContent = "Off"
  } else {
    statusEl.textContent = deafened ? "Deafened" : "Listening"
  }
}

async function setState(target) {
  render(await browser.runtime.sendMessage({ type: "set_listening", state: target }))
}

powerBtn.addEventListener("click", () => {
  setState(current.state === "off" ? "listening" : "off")
})

deafenBtn.addEventListener("click", () => {
  setState(current.state === "deafened" ? "listening" : "deafened")
})

// Voice-initiated changes ("<wake> deafen"/"<wake> listen") while the popup is open.
browser.runtime.onMessage.addListener(message => {
  if (message && message.type === "listening_state_changed") {
    render(message.state)
  }
})

async function init() {
  render(await browser.runtime.sendMessage({ type: "get_listening_state" }))
}

init()
