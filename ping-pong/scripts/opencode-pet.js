// Ping-pong pet for OpenCode: a toast when the ball is served to a player and when the rally ends.
// Installed by setup_pet.py into ~/.config/opencode/plugins/. Reads ~/.ping-pong/active.json.
import { readFileSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

const ACTIVE = join(homedir(), ".ping-pong", "active.json")
const LANE = 21

function readState() {
  try {
    const { state } = JSON.parse(readFileSync(ACTIVE, "utf8"))
    return JSON.parse(readFileSync(state, "utf8"))
  } catch {
    return null
  }
}

function lane(side) {
  const pos = side === 0 ? 2 : LANE - 3
  let cells = ""
  for (let i = 0; i < LANE; i++) cells += i === pos ? "●" : i === Math.floor(LANE / 2) ? "┆" : "·"
  return `▌${cells}▐`
}

export const PingPongPet = async ({ client }) => {
  let seen = null
  const toast = (title, message, variant = "info") =>
    client.tui.showToast({ body: { title, message, variant, duration: 7000 } }).catch(() => {})

  setInterval(() => {
    const s = readState()
    if (!s) return
    const key = [s.started_at, s.hits.length, s.current?.n, s.current?.side, s.status].join(":")
    if (key === seen) return
    const firstLook = seen === null
    seen = key
    if (firstLook && s.status !== "running") return // ignore rallies that ended before OpenCode started

    const [a, b] = s.players.map(p => p.label)
    const last = s.hits.at(-1)
    const lastLine = last ? `\n${last.player}: ${(last.changes[0] || "returned the ball").slice(0, 80)}` : ""
    if (s.status === "done") return toast("🏓 Rally done", `${s.hits.length} hits, ${a} vs ${b}.${lastLine}`, "success")
    if (s.status === "error") return toast("🏓 Rally stopped", "Two faults in a row.", "error")
    if (s.current) {
      const who = s.players[s.current.side].label
      toast(`🏓 Hit ${s.current.n}/${s.iterations}: ${who}`, `${a} ${lane(s.current.side)} ${b}${lastLine}`)
    }
  }, 1500)

  return {}
}
