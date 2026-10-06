<img src="assets/icon.svg" width="64" height="64" alt="">

# ping-pong

A skill that makes two agent CLI sessions rally one idea back and forth until it is sharp, then turns
the last version into something you can act on — a plan, a one-shot build prompt, or a ticket-ready spec.

```
/ping-pong 10 I have a business idea that is Tinder but for houses
```

Ten alternating turns, normally five per player. Each **hit** is one model receiving the current
version plus its opponent's notes, critiquing it, and returning an improved version. Early hits open
the idea up, middle hits deepen it, late hits converge. Your host agent is the umpire: it starts the
rally, follows it, and writes the deliverable.

Both players can be the same CLI. The engine is Python 3.9+, standard library only — no dependencies
to install, no API key required if you are already logged into an agent CLI.

- [Install](#install) · [Quick start](#quick-start) · [Usage](#usage) · [Settings](#settings) · [Files](#files-it-writes) · [Troubleshooting](#troubleshooting)

---

## Install

The skill is the `ping-pong/` folder. Put it in your host's skills directory.

### Option A — drop in the zip (Claude Code, Cursor, Codex, OpenCode)

Build the bundle:

```sh
./package-skill.sh          # writes dist/ping-pong-skill.zip
```

Then unzip it into your host's skills directory:

| Host | Directory |
|---|---|
| Claude Code | `~/.claude/skills/` |
| Cursor | `~/.cursor/skills/` (also reads `~/.claude/skills/`) |
| Codex | `~/.codex/skills/` |
| OpenCode | `~/.config/opencode/skills/` |

```sh
unzip dist/ping-pong-skill.zip -d ~/.claude/skills/
```

The zip has a single top-level `ping-pong/` folder with `SKILL.md` at its root, so it also matches the
layout claude.ai expects for an uploaded skill. One caveat worth knowing before you upload it there:
the rally works by launching agent CLIs on your machine, and the claude.ai sandbox has none, so only
`mock:` players will actually run in chat. Use it in Claude Code or another local host for real rallies.

### Option B — copy the folder

```sh
git clone https://github.com/Statse/ping-pong-skill.git
cp -r ping-pong-skill/ping-pong ~/.claude/skills/
```

### Verify the install

```sh
cd ~/.claude/skills/ping-pong
python3 scripts/rally.py doctor          # which player CLIs are on PATH
python3 scripts/rally.py --list-players  # what it would pick for you
```

`doctor` reports availability only; it does not check that you are logged in or that a model is
reachable. Then restart your host (or start a new session) so it picks up the new skill.

---

## Quick start

A credential-free dry run with fake players, about 15 seconds:

```sh
python3 scripts/rally.py --idea "test" -n 4 --players mock:left,mock:right --no-animation
```

A real rally:

```sh
python3 scripts/rally.py --idea "Tinder for houses" -n 10 --players cli:claude,cli:codex
```

Or just ask your agent: `/ping-pong 10 Tinder for houses`. It will pick players, start the rally in the
background, follow it, and write the deliverable for you.

A ten-hit rally between two real CLIs takes a while — each hit is a full agent session. Run it in the
background and follow the event stream rather than blocking on it.

---

## Usage

### Starting a rally

```
python3 scripts/rally.py [--idea TEXT | --idea-file PATH] [-n N] [--players A,B]
                         [--out DIR] [--animation | --no-animation]
```

| Flag | Default | What it does |
|---|---|---|
| `--idea TEXT` | — | The idea as text. One of `--idea` / `--idea-file` is required. |
| `--idea-file PATH` | — | Read the idea from a file. Use this for anything longer than a sentence. |
| `-n`, `--iterations N` | `6` | Total alternating turns, not turns per player. `-n 10` is five each. |
| `--players A,B` | auto | Exactly two specs, comma-separated. See [PLAYERS.md](ping-pong/PLAYERS.md). |
| `--out DIR` | `./.ping-pong/<timestamp>-<slug>-<random>` | Where the rally is written. Must not already hold a rally. |
| `--animation` | off | Expose the optional pixel widget on a loopback port. Nothing opens a browser. |
| `--no-animation` | — | Disable the display for this one rally. Mutually exclusive with `--animation`. |
| `--list-players` | — | Print detected players and the auto pick, then exit. |

Exit codes: `0` the rally finished, `130` it was cancelled, `1` it ended in an error, `2` the arguments
or player setup were wrong.

### Players

A spec is `kind:name[:model]`. The short version:

- **Agent CLIs** — `cli:claude`, `cli:codex`, `cli:cursor`, `cli:opencode`, `cli:copilot`,
  `cli:gemini`, or `cli:<any-command>`. No API key needed if you are logged in. Each call runs in a
  fresh temp directory so the CLI cannot touch your repo.
- **APIs** — `anthropic:<model>`, `openai:<model>`, `gemini:<model>`, `openrouter:<vendor/model>`,
  each needing its key in the environment.
- **Testing** — `mock:left`, `mock:right` return canned replies after a short delay.

Without `--players`, the engine detects CLIs first, then API keys, and prefers two different vendors.
With only Claude available it plays Opus against Sonnet. Full tables, model overrides and the
auto-pick rules are in [PLAYERS.md](ping-pong/PLAYERS.md).

### Following a rally

```sh
python3 scripts/rally.py status --dir D                              # one plain status line
python3 scripts/rally.py wait --dir D --after 0 --timeout 60          # block for the next event
```

`wait` returns one event and prints its ID; pass that ID as the next `--after` to walk the stream in
order. Exit codes: `0` an event arrived, `2` the timeout expired, `1` the rally could not be read.
With no `--after` on a finished rally it reports the terminal event immediately. Both commands fall
back to the active rally when `--dir` is omitted.

Event types, in order: `serve`, then `hit` or `fault` per turn, then one of `done`, `error`, `stopped`.

Both commands also print the last hit's drift in plain language:

```
Rally done: 4/4 turns completed. Last hit rewrote 25 % of lines, 1.00x the length.
```

That is the honest measure of whether the players are refining the idea or quietly rewriting it. Every
hit stores `lines_kept` (the share of the incoming version's substantial lines kept verbatim) and
`size_ratio` (outgoing length over incoming) in `state.json`. The serve reports both as `null`, having
nothing to compare against.

### The optional display

Two pixel paddles exchange one ball while the rally runs. That is all it is — no scores, no turn
tracking, no dashboard. It stops on completion, error, cancellation or engine disconnection, and shows
a still illustration under a reduced-motion preference. The rally is unaffected by turning it off.

`--animation` prints an `animation: http://127.0.0.1:<port>/` URL for a host that can embed a local
page. It never launches a browser, and only lifecycle status and the display preference are served —
your idea and the players' responses are not. Native placement in a chat UI needs a host adapter;
installing this skill does not provide one. See [DISPLAY.md](ping-pong/DISPLAY.md) and the
[host support research](docs/host-animation-support.md).

---

## Settings

### Persistent preference

One setting, stored as `animation` in `~/.ping-pong/settings.json`:

```sh
python3 scripts/rally.py animation off      # disable future animations
python3 scripts/rally.py animation on       # enable them again
python3 scripts/rally.py animation status   # print the current preference
```

Default is on. Changing it never interrupts a running rally. A persistent **off** beats a per-run
`--animation` request, so once you turn it off it stays off until you turn it back on. In an embedded
widget, unchecking **Animation** does the same thing and saves the preference. An unreadable or
malformed settings file is treated as off — a broken preference must not force motion on.

### Environment variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Required for `anthropic:` players |
| `OPENAI_API_KEY` | Required for `openai:` players |
| `GEMINI_API_KEY` | Required for `gemini:` players |
| `OPENROUTER_API_KEY` | Required for `openrouter:` players |
| `PINGPONG_ANTHROPIC_MODEL` | Default model for `anthropic:` without an explicit model |
| `PINGPONG_OPENAI_MODEL` | Default model for `openai:` |
| `PINGPONG_GEMINI_MODEL` | Default model for `gemini:` |
| `PINGPONG_OPENROUTER_MODEL` | Default model for `openrouter:` |

Agent CLI players need no variables — they use whatever login the CLI already has. Model names change
often; if a built-in default is rejected, set the variable or name the model in the spec.

### Timeouts and limits

These are fixed in the engine rather than configurable: 1800 s per CLI call, 900 s per API call, one
retry per hit, and two consecutive faults end the rally with `status: error`. A fault switches sides so
the opponent takes the hit. Time budgets and graceful resume are planned, not built.

---

## Files it writes

| Path | What it is |
|---|---|
| `~/.ping-pong/settings.json` | Your persistent `animation` preference |
| `~/.ping-pong/active.json` | Pointer to the most recently started rally, so `status` and `wait` work without `--dir` |
| `<rally dir>/state.json` | Full rally state, rewritten atomically after every transition |
| `<rally dir>/events.jsonl` | Append-only ordered event log, one JSON object per line |
| `<rally dir>/final.md` | The last version plus every open question raised during the rally |
| `<rally dir>/deliverable.md` | Written by the host agent in step 6, not by the engine |

The rally directory defaults to `./.ping-pong/<timestamp>-<slug>-<random>` in your working directory.
`state.json` is always replaced before its event is appended, so a reader may see newer state than the
event it is reading, never older. Your idea and the players' replies stay on your machine; nothing is
uploaded anywhere except to whichever model provider you chose as a player.

---

## Troubleshooting

**"Need exactly two players"** — nothing was detected. Run `scripts/rally.py doctor`, then log into an
agent CLI or export an API key. [PLAYERS.md](ping-pong/PLAYERS.md) has the setup per player.

**A player faults every turn** — the CLI is on PATH but not usable: not logged in, or the model alias
in your spec does not exist for that tool. The fault message in `state.json` carries the CLI's own
stderr. Try the bare spec (`cli:claude` rather than `cli:claude:opus`) first.

**"rally already exists in ..."** — `--out` points at a directory that already has a rally in it. Pick a
new one; the engine will not overwrite the state behind an existing event stream.

**The rally ended with two faults** — two consecutive failures stop it on purpose rather than burning
your quota. `final.md` still holds the best version reached. Restart with different players.

**No animation appears** — expected unless your host can embed a local page. Check the preference with
`animation status`, and remember a persistent off overrides `--animation`.

**Ctrl-C** — records `status: stopped`, keeps every completed turn, and still writes `final.md`.

---

## Development

```sh
python3 -m unittest discover -s tests -v     # credential-free; ~20 s
./package-skill.sh                           # rebuild dist/ping-pong-skill.zip
```

The engine stays Python 3.9-compatible and standard-library-only; CI runs 3.9 and 3.12 across Linux,
macOS and Windows (mock rally + `doctor` with an empty PATH + the unit suite). Windows is
best-effort until a live rally is verified there. Prefer `rally.py wait --timeout N` over the shell
`timeout(1)` utility — it is absent on macOS. `tests/test_compatibility.py` guards the version
floor. Roadmap and slice-by-slice acceptance criteria live in [SPEC-v2.md](SPEC-v2.md) and the
repository's [issues](https://github.com/Statse/ping-pong-skill/issues).

Created in [T3 Code](https://t3.codes).
