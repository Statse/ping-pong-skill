# Spec: ping-pong v2

A ticket-ready spec for the next version of the `ping-pong` agent skill. Shaped as vertical slices so
`/to-tickets` or `/to-issues` can cut it directly.

Scope decisions taken by the owner during this refinement are listed under
[Decisions](#decisions-taken-in-this-refinement). Everything here is bounded by the original
constraints: **stdlib Python only, no installs, `SKILL.md` under ~100 lines, the ping-pong visual stays
the signature element.**

---

## Problem and goal

v1 works. A real 4-hit rally (Claude Code vs Codex) ran to completion with zero faults, and all three
locally installed CLIs returned clean, parseable JSON on the first try. The v1 worry list was mostly
wrong about *where* the fragility is.

The measured problem is different and worse: **the rally does not refine an idea, it rewrites it, and it
grows without bound.** Across four hits the idea went 4.5 KB → 7.5 KB → 15.9 KB → 19.7 KB → 20.2 KB
while retaining **0–1 % of its substantial lines verbatim** at each hit. The "close" phase, which is
supposed to converge, grew the document and silently dropped every open question. An idea owner who asks
for 10 hits today gets a 40 KB document that shares almost no sentences with the version they approved at
hit 3.

**Goal for v2:** the rally provably *keeps* what is good, converges instead of inflating, fails loudly
instead of silently, lets the owner interject, and is watchable without the umpire guessing when to look.

### Evidence

Measured on macOS 15 (darwin 25.2.0), Python 3.9.6, 2026-10-06. Raw data in [`docs/evidence/`](docs/evidence/).

| Check | Result |
|---|---|
| `cli:claude` single hit (`claude --model M -p`) | OK, 25 s, 3.9 KB, JSON parsed |
| `cli:codex` single hit (`codex exec --skip-git-repo-check --output-last-message`) | OK, 35 s, 2.8 KB, JSON parsed |
| `cli:cursor` single hit (`agent -p --trust --mode ask --output-format text`) | OK, 16 s, 2.6 KB, JSON parsed |
| Full 4-hit rally, claude vs codex, 4.5 KB idea | `status: done`, 0 faults, 4/4 parsed |
| Per-hit latency across the rally | 59 s → 124 s → 181 s → 136 s (grows with context) |
| Version size across the rally | 4.5 KB → 7.5 KB → 15.9 KB → 19.7 KB → 20.2 KB |
| Substantial lines (>20 chars) kept verbatim per hit | 0 %, 1 %, 0 %, 1 % |
| Vocabulary (4+ char words) overlap per hit | 59 %, 61 %, 53 %, 68 % |
| `difflib` char similarity between consecutive versions | 0.04–0.10 |
| Open questions carried by the final hit | 7 at hit 3 → **0** at hit 4 |
| Python floor | 3.9.6 runs v1 unmodified; keep 3.9 as the floor |

Two things this evidence killed:

- **Replacing the JSON reply envelope with a section-delimited one.** I expected long markdown inside a
  JSON string to break escaping. It did not, at 20 KB, on two different CLIs. The envelope stays; the fix
  is to treat an *unparsed* reply as a fault instead of silently accepting the raw text as the version
  (v1 `parse_reply` does accept it, `parsed: False`).
- **Using `claude --bare` for a clean, hook-free player.** `--bare` restricts Anthropic auth to
  `ANTHROPIC_API_KEY` only and never reads OAuth or the keychain, so on a logged-in machine with no key
  it exits 1 with `Not logged in`. Verified. Do not use it. The existing temp-cwd isolation already keeps
  project-level `CLAUDE.md`/hooks out; user-level config still applies and that is acceptable.

---

## Users and main flows

One user: the idea's owner, working inside a coding agent (Claude Code, Codex CLI, Cursor CLI, or any of
their GUI versions). The agent is the umpire.

1. **Rally** — owner gives an idea and a hit count; umpire picks two players, starts the engine, shows
   the rally, and hands back a deliverable.
2. **Watch** — owner follows the browser court, or the ASCII frames the umpire pastes in chat, or both.
3. **Interject** — owner answers an open question or adds a constraint mid-rally; the next hit must
   honour it.
4. **Recover** — a player faults, the owner cancels, or the machine sleeps; the rally resumes or ends
   with a usable artifact either way.

---

## Architecture

```
ping-pong/
  SKILL.md          ≤100 lines, 7 steps, unchanged shape
  PLAYERS.md        three players, doctor output, how to override adapters
  PROTOCOL.md       new: the hit contract, the ledger, phases, length budgets
  OUTPUTS.md        deliverable templates (minor edits)
  players.json      new: adapter table (argv templates), overridable
  scripts/
    rally.py        engine + subcommands + frame renderer
    court.html      live court, served read-only; also the offline replay
```

v2 **deletes** `scripts/pet.py`, `scripts/setup_pet.py`, `scripts/opencode-pet.js` and `DISPLAY.md`'s pet
table. Two artifacts remain: the browser court and the ASCII frame. The frame renderer moves from
`pet.py --frame` to `rally.py frame`.

### Players

Three, plus mocks. No API transports, no other CLIs.

| Spec | Invocation | Vendor |
|---|---|---|
| `cli:claude[:model]` | `claude [--model M] -p <prompt>` | anthropic |
| `cli:codex[:model]` | `codex exec --skip-git-repo-check --sandbox read-only --output-last-message F [-m M] <prompt>` | openai |
| `cli:cursor[:model]` | `agent -p --trust --mode ask --output-format text [--model M] <prompt>` | derived from the model name |
| `mock:<name>` | scripted, for tests and demos | — |

**Two players may be the same CLI.** The point of the rally is two independent agent sessions arguing
about one idea, not two vendors. `cli:claude` vs `cli:claude`, or `cli:claude:opus` vs
`cli:claude:sonnet`, is a first-class configuration — not a degraded fallback. This drops the v1
"different LLMs" promise, and with it the entire vendor-distinctness problem.

Vendor is still *recorded* where it is knowable, because it is useful information on the court and in
`final.md`. It is never a requirement and never a warning. `cursor-agent --list-models` on this machine
offers `gpt-5.3-codex*`, `gpt-5.2`, `claude-*`, `cursor-grok-4.5-*`, `gemini-3.7-flash-high` and
`composer-2.5`, so an owner who *wants* vendor variety can pin it; `doctor --models` lists what is
available.

### Engine state

`<out>/state.json` — atomic write after every transition (v1 already does this). Adds `ledger`,
`drift` per hit, `shape`, `budget`, and `stopped_reason`.

`<out>/events.jsonl` — new, append-only, one JSON line per event:
`serve`, `hit`, `let`, `fault`, `note`, `break`, `done`, `error`, `stopped`. This is what `rally.py wait`
blocks on, and it makes the umpire's polling event-driven instead of a one-minute guess.

---

## Vertical slices

Ordered. Each is thin, end-to-end and demoable on its own. Every slice must keep the mock rally green:
`rally.py --idea "test" -n 4 --players mock:left,mock:right`.

### 1. Watchable rally, event-driven — delivers: the umpire stops guessing when to look — depends on: none

The whole display path, with no change to the hit protocol.

- `events.jsonl`, appended before `state.json` is replaced, so a reader never sees an event for a state
  that is not on disk yet.
- `rally.py wait [--dir D] [--after N] [--timeout S]` blocks until the next event after cursor `N`,
  prints the ASCII frame plus a one-line event summary, and exits: `0` new event, `2` timeout,
  `1` rally ended in error. Default `--timeout 180`.
- `rally.py frame [--dir D]` — v1's `pet.py --frame`, moved. Shows score, ball, phase, elapsed, last
  change, and the new drift line once slice 2 lands.
- Court served on a free port (`bind to :0`, print the real URL); `--port` still honoured and still
  127.0.0.1-only, GET-only.
- `--linger` default 4 s → 300 s, and the final output names `replay.html` as the offline artifact.
- Remove the Google Fonts `<link>` from `court.html` so `replay.html` is genuinely offline; fall back to
  the existing system font stack.
- `--no-browser` becomes automatic when there is no display (no `DISPLAY`/`WAYLAND_DISPLAY` on Linux,
  `SSH_CONNECTION` set).

**Acceptance**
- A 4-hit mock rally: `wait` returns once per event, in order, with no gaps and no repeats, when called
  in a loop with `--after` from the previous call.
- Two rallies start concurrently without a port collision; both courts load.
- `replay.html` opened from `file://` with networking disabled renders fully, auto-plays the replay, and
  the copy button works.
- `wait` on a finished rally returns immediately with the `done` event; on a rally dir that does not
  exist, exits non-zero with a clear message.
- `wait --timeout 1` on a mid-hit rally exits 2 and prints a frame anyway.

### 2. The idea stops drifting — delivers: refinement instead of rewriting — depends on: 1

The core fix, aimed straight at the measured 0–1 % line retention and 4.5× growth.

- **Ledger.** `state.json.ledger` is a list of `{id, by, text, status, reason}`. `O-*` entries are the
  owner's non-negotiables; `P-*` are decisions a player made. Every prompt carries the full ledger,
  compact, capped at 25 entries (oldest `P-*` entries fall off first, never `O-*`).
- Seeded before the serve from `constraints.md` in the rally dir if present (one bullet per line), which
  the umpire writes from the owner's brief. For this very idea the seeds would be: stdlib only; no
  installs; `SKILL.md` ≤100 lines; keep the ping-pong visual.
- The reply envelope gains `decisions`: a list of `{op: "add"|"drop", id?, text?, reason?}`. A `drop`
  without a reason is rejected. A `drop` of an `O-*` entry is **refused** by the engine and recorded as a
  dispute, which surfaces in the court and in `final.md`.
- **Length budget.** Each prompt states a hard character budget for `version`, derived from the length of
  the version it received: open ≤ 1.6×, deepen ≤ 1.3×, close ≤ 1.0×. The close phase must not grow at
  all.
- A close-phase version over its budget by more than 10 % is a **let**: one retry quoting the overage and
  the instruction to cut, then accept with `over_budget: true` flagged in state. A let is not a fault and
  does not count toward the fault limit.
- **Drift telemetry.** The engine computes, per hit, `lines_kept` (share of the incoming version's
  >20-char lines present verbatim) and `size_ratio`, and stores them in `state.json`. The frame and the
  court show them ("rewrote 99 % of lines"). This is how the fix gets verified in the wild, not just in
  tests.
- The close-phase prompt adds: preserve the exact wording of any section you are not improving.
- **Scoreboard becomes honest.** Court points per player = that player's `P-*` ledger entries still
  standing. v1's points (hits taken) were meaningless, since both players always take the same number.

**Acceptance**
- A scripted mock that tries to drop `O-1` gets the drop refused, the rally continues, and the dispute
  appears in `state.json`, the court and `final.md`.
- A scripted mock that returns a close-phase version 50 % longer than its input triggers exactly one let,
  then the hit is accepted with `over_budget: true`.
- `lines_kept` and `size_ratio` are present for every hit in `state.json` and rendered in `rally.py frame`.
- Re-run of the dogfood rally (same idea, 4 hits, claude vs codex): median `lines_kept` is materially
  above the measured 0–1 % baseline, and the final version is no longer than the version at hit 3.
  Record the new numbers in `docs/evidence/`.
- The ledger cap never evicts an `O-*` entry, proven with a 40-entry fixture.

### 3. Loud, recoverable failure — delivers: no silent garbage, no lost rally — depends on: 1

- **Fault taxonomy.** Retryable: timeout, non-zero exit with a transient message, empty output,
  unparseable reply. Fatal: missing binary, auth failure, unknown model. Fatal skips the retry and goes
  straight to the opponent, or aborts with the exact remedy in the message.
- Retries back off 5 s then 20 s. v1 retries instantly, which makes a rate limit burn both attempts.
- **An unparsed reply is a fault**, not a version. v1 accepts the raw CLI text as the version with
  `parsed: False`. v2 retries once with a terse "reply with only the JSON object" reminder, then hands the
  hit to the opponent.
- **Hit parity.** When the opponent covers a fault, record `covered_for` and keep alternating afterwards
  so totals stay as balanced as the fault count allows. v1 silently inverts the order and breaks the
  documented "an even number gives both players the same number of hits" promise. Report the final
  per-player hit counts in `final.md`.
- **Budgets.** `--hit-timeout` default 600 s (measured worst case 181 s), `--budget-minutes` default 45
  wall clock. Hitting a budget stops cleanly with `stopped_reason: budget`; it never triggers an extra
  unbudgeted rewrite.
- `rally.py stop --dir D` — graceful: the current hit finishes, then the rally stops with
  `status: stopped` and writes `final.md`. Ctrl-C does the same. A second Ctrl-C kills the child process
  group.
- `rally.py resume --dir D [-n extra]` — continues from the next hit with the same players and ledger,
  appending to `events.jsonl`.

**Acceptance**
- Mocks for each fault class: each produces the documented action, the right `events.jsonl` entry, and
  the right court symbol.
- A mock returning prose instead of JSON never becomes a `version`; it produces a fault and a retry.
- Kill the engine mid-hit, then `resume`: completed hits appear exactly once, the ledger is intact, and
  the abandoned hit is labelled, not counted.
- `stop` during hit 2 of 6 leaves `status: stopped`, a valid `final.md`, and no further player calls
  (assert on the invocation log).
- A 1-minute `--budget-minutes` on a mock rally stops with `stopped_reason: budget` and a usable artifact.

### 4. Certified players — delivers: setup failures diagnosed in 30 s, not 10 min — depends on: 1

- **`players.json`** adapter table shipped in the skill, overridden by `~/.ping-pong/players.json` if
  present. One entry per tool: `bin` candidates, `argv` template with `{prompt}`/`{model}`/`{outfile}`
  placeholders, `output: stdout|file`, and `env` overrides (`NO_COLOR=1`, `TERM=dumb`). Flag churn becomes
  a data edit, not a code change.
- **`rally.py doctor [--players ...]`** probes each candidate with a real, tiny envelope prompt and
  prints a table: binary found, version string, latency, exit code, parsed yes/no, derived vendor.
  Caches to `~/.ping-pong/doctor.json`, 7-day TTL, keyed on the tool's version string. Only the chosen
  pair is probed before a rally.
- A **preflight** probe of both chosen players runs before the serve unless cached and fresh. A player
  that fails preflight is reported with its remedy and the rally does not start.
- **Same-CLI rallies are first-class.** Auto-pick takes the two best-ranked available players, same tool
  or not. With one CLI installed it pairs that tool with itself, preferring two different model aliases
  when the tool exposes them (`cli:claude:opus` vs `cli:claude:sonnet`) and falling back to the plain
  spec twice. There is no "need exactly two players" dead end any more, and no warning: one CLI is a
  supported setup.
- **Vendor is information, not a constraint.** Recorded as `anthropic`/`openai` for
  `cli:claude`/`cli:codex`, and for `cli:cursor` derived from the model name (`claude-*` → anthropic,
  `gpt-*`/`*codex*` → openai, `*grok*` → xai, `gemini-*` → google, `composer-*`/`auto` → unknown). Shown
  on the court and in `final.md`. Never gates a rally.
- `doctor --models` lists each tool's available models, so an owner who wants vendor variety or two
  distinct models can pick deliberately.
- Drop every "two different LLMs" claim from `SKILL.md`, `PLAYERS.md` and the skill description: the
  rally is between two agent CLI sessions.
- Record the exact tested CLI versions in `PLAYERS.md`, with the date.

**Acceptance**
- `doctor` on this machine shows all three CLIs OK with latency and vendor, and the cache makes a second
  run return in under a second.
- Renaming a flag in `~/.ping-pong/players.json` changes the invocation, proven by the invocation log,
  with no edit to `rally.py`.
- A player with a bogus model name fails preflight in under 60 s with a message naming the model and the
  fix; no rally directory is left half-written.
- A full live rally with `cli:cursor` as one of the two players completes.
- A full live rally of `cli:claude` against itself completes, and the court labels both players
  distinguishably (tool + model + side).
- With only one CLI on `PATH`, `--list-players` proposes a valid pair and the rally runs; no warning, no
  error.

### 5. The owner can interject — delivers: open questions get answered mid-rally — depends on: 2

- **Inbox.** `<out>/inbox.md`. Before each hit the engine reads it; if non-empty, the content is injected
  into the prompt as the owner's note, under a heading that states it outranks both players, then moved to
  `notes/<n>.md` and the file is emptied. An `note` event is appended.
- `rally.py note --dir D "text"` writes to the inbox, so the umpire can relay a chat message without the
  owner leaving the agent.
- An owner note that answers an open question becomes a **persistent `O-*` ledger entry**, not a one-shot
  aside, so it survives every later hit. This is the fix for hit 4 reporting zero open questions after hit
  3 raised seven.
- **Question triage.** The final hit receives the accumulated, deduplicated open-question list and must
  return each one as `answered` (with the answer), `kept` (still needs the owner), or `dropped` (with a
  reason). `final.md` prints the three groups separately. v1 dumps every question ever raised, including
  ones already resolved.
- **Phase breaks.** `--breaks` (off by default) pauses at phase boundaries, at most twice, emits a `break`
  event with the blocking questions, and waits up to `--break-timeout` (default 300 s) for an inbox note
  before continuing. Silence continues the rally; it never hangs forever.

**Acceptance**
- A note dropped into `inbox.md` during hit 2 appears verbatim in hit 3's prompt (assert on the captured
  prompt), is consumed exactly once, and is present as an `O-*` entry in hit 6's prompt.
- Two notes written before the same hit are both delivered, in order.
- A note written while no rally is running is reported, not silently lost.
- With `--breaks`, the rally pauses exactly twice, emits `break` events with the questions, and continues
  on timeout with `break: timeout` recorded.
- `final.md` for the dogfood rally shows answered / still-open / dropped questions as three groups, with
  no question appearing twice.

### 6. A deliverable you can act on — delivers: the umpire's judgment becomes a rule — depends on: 2, 5

- The final hit returns `shape: {units, blocking_decisions, one_session, rationale}` — how many
  independently deployable units the idea needs, how many decisions still block a build, and whether
  acceptance is checkable in one agent session.
- **The classification becomes deterministic.** One-shot build prompt iff `units == 1` **and**
  `blocking_decisions == 0` **and** `one_session == true`. Otherwise a sliced, ticket-ready spec. Non-code
  if the final version names no build artifact. The umpire records the three inputs and the resulting
  branch in the deliverable, so the call is auditable instead of a judgment call. Players report evidence;
  they do not vote.
- `final.md` gains: decisions still standing (per player), disputes, the three question groups, drift and
  size per hit, per-player hit counts, and the rally's wall-clock time.
- Court gains three read-only panels: ledger (decisions standing, disputes), open questions, and a
  drift/size meter per hit. Still GET-only, still 127.0.0.1.
- `OUTPUTS.md`: add a "How this shape was chosen" line to both code templates.
- **`SKILL.md` rewrite**, still ≤100 lines and still 7 steps, with: `doctor` in step 2, `wait` as the only
  polling primitive in step 4 (no more "about once a minute"), the inbox offered once in step 4, and the
  deterministic shape rule in step 6. The pet paragraph is deleted.
- One-line privacy notice before the first serve naming the providers the idea will be sent to, plus an
  offer to add `.ping-pong/` to the repo's `.gitignore`.

**Acceptance**
- Three reference ideas — a non-code brief, a single-file CLI tool, a multi-service feature — each produce
  the shape the rule predicts, with the inputs recorded.
- A final hit that omits `shape` falls back to the umpire's judgment and says so in the deliverable; it
  does not crash.
- `SKILL.md` is ≤100 lines, and a fresh agent session following it end-to-end on a mock rally produces a
  `deliverable.md`.
- The court's three panels render for a finished rally and for one that stopped with faults.
- `final.md` never loses a decision that no player dropped, proven against the dogfood ledger.

### 7. Portability floor — delivers: it keeps working on the next machine — depends on: 1

- GitHub Actions matrix: Python 3.9 and 3.12 × ubuntu-latest, macos-latest, windows-latest, running the
  mock rally, `doctor` with no CLIs installed, and the parser fixtures. Stdlib-only means no install step.
- No 3.10+ syntax (no `match`, no `X | Y` annotations). 3.9.6 is the verified floor.
- Windows is **best-effort**: the mock rally and `wait` must pass in CI; nothing claims verified Windows
  support until someone runs a live rally there. Use `subprocess.list2cmdline` on Windows where v1 uses
  `shlex.quote`, and `taskkill /T` for process-group kill.
- Documentation must not use `timeout(1)` in examples; it is absent on macOS.

**Acceptance**
- CI green on all six cells.
- `doctor` on a machine with no CLIs exits non-zero with a setup message and no traceback.
- A grep for `match `/`|` annotations/3.10+ builtins in `scripts/` is clean.

---

## Decisions taken in this refinement

| Decision | Why |
|---|---|
| Players are `cli:claude`, `cli:codex`, `cli:cursor` and `mock:` only | Owner's call. Deletes the four API transports, their key detection, and the whole "default model names go stale" weak spot. All three are testable on this machine. |
| No pet in v2 | Owner's call: "not just yet, and it needs to be toggleable anyway." Deletes three scripts and the uneven-host problem. Court + frames become the baseline and must be good. |
| Play all N hits; the last version wins | Owner's call. No judge model, no self-scoring, no early stop. Convergence is enforced by the per-phase length budget instead, which is deterministic and free. |
| The JSON reply envelope stays | Tested at 20 KB on two CLIs with zero parse failures. The real bug is accepting an *unparsed* reply as a version. |
| No `claude --bare` | Tested: it restricts auth to `ANTHROPIC_API_KEY` and fails on a logged-in machine with no key. |
| No third judge model | Adds a vendor dependency, cost and complexity for a ranking that self-scoring cannot be trusted to produce. |
| Anti-drift is slice 2, not slice 6 | It is the only measured failure. Everything else on the v1 worry list was speculative. |
| A rally may use one CLI against itself | Owner's call: the rally is between two agent CLI sessions, not two vendors. Removes the "different LLMs" promise, the vendor-distinctness warnings and the one-CLI dead end. Vendor stays as information only. |
| `wait` replaces timed polling | The umpire pasting a frame "about once a minute" wastes tokens on unchanged frames and misses fast hits. Events are cheap and exact. |
| macOS/Linux certified, Windows best-effort in CI | Owner's call. No Windows machine to verify a live rally on, so the claim would be unfounded. |
| Python 3.9 floor | Verified working; raising it buys nothing. |

## Open questions

Blocking first.

1. **Ledger seeding.** Should the umpire always write `constraints.md` before the serve (one more step,
   better anchoring), or only when the owner's brief contains explicit non-negotiables? Slice 2 assumes
   "always, and it may be empty".
2. **Length budget multipliers.** Open 1.6× / deepen 1.3× / close 1.0× are inferred from one rally. They
   need a second data point at `n=8` before they are fixed defaults.
3. **Drift threshold.** Should a hit that keeps under some floor of the incoming lines be a let, like an
   over-budget hit? Tempting, but a legitimate rewrite exists (the owner's note changes direction), so
   slice 2 only *measures* it. Revisit after the re-run in slice 2's acceptance.
4. Default `n`: keep 6? At measured latencies, 6 hits on a 4.5 KB idea is roughly 10–12 minutes, and
   per-hit latency grows with context.
5. Should rally artifacts stay in the repo's `.ping-pong/` (gitignored, easy to find) or move to
   `~/.ping-pong/runs/` so the engine never writes inside the user's repo at all?
6. Should `--breaks` default on in interactive hosts? Slice 5 ships it off.

## Out of scope

- The in-host pet (Claude Code statusline, Cursor footer, OpenCode toasts) — and when it returns it must
  be a toggle, not a config hijack.
- Any player other than Claude Code, Codex and Cursor CLI: no OpenCode, Copilot or Gemini CLI, no direct
  Anthropic/OpenAI/Gemini/OpenRouter API transports.
- A judge or scoring model; "keep the best version" rather than the last.
- Convergence-based early stopping.
- Browser-side controls: the court stays read-only. Control goes through `rally.py` and the chat.
- Verified Windows support, beyond the CI mock rally.
- Rallying against an existing codebase (a repo context brief for the players).
- Cost estimation or a price table.
