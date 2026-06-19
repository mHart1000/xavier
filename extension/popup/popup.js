/**
 * Xavier popup - a single power button that toggles voice control.
 *
 * The mic is owned by the daemon, so the button only talks to the background
 * script, which relays the on/off state down the Native Messaging port.
 */

const powerBtn = document.getElementById("power")
const statusEl = document.getElementById("status")

function render({ listening, connected }) {
  powerBtn.classList.toggle("on", listening)
  powerBtn.setAttribute("aria-pressed", String(listening))

  if (!connected) {
    statusEl.textContent = "Daemon not connected"
  } else {
    statusEl.textContent = listening ? "Listening" : "Off"
  }
}

async function init() {
  const state = await browser.runtime.sendMessage({ type: "get_listening_state" })
  render(state)
}

powerBtn.addEventListener("click", async () => {
  const enabled = !powerBtn.classList.contains("on")
  const state = await browser.runtime.sendMessage({ type: "set_listening", enabled })
  render(state)
})

init()
