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

### Option A — drop in the zip (Claude Code, Cursor, Codex)

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
mkdir -p ~/.codex/skills
cp -R ping-pong-skill/ping-pong ~/.codex/skills/
```

For Claude Code, replace `~/.codex/skills` with `~/.claude/skills`; for Cursor, use
`~/.cursor/skills`.

### Verify the install

```sh
cd ~/.codex/skills/ping-pong
python3 scripts/rally.py doctor          # preflight an auto-picked pair
python3 scripts/rally.py --list-players  # what it would pick for you
```

`doctor` sends a small format probe to both selected players, so it checks authentication and model
access as well as installation. Restart your host (or start a new session) so it picks up the skill.

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
| `-n`, `--iterations N` | `10` | Total alternating turns, not turns per player. `-n 14` is seven each. |
| `--players A,B` | auto | Exactly two specs, comma-separated. See [PLAYERS.md](ping-pong/PLAYERS.md). |
| `--out DIR` | `./.ping-pong/<timestamp>-<slug>-<random>` | Where the rally is written, normally the directory printed by `setup`. Must not already hold a rally. |
| `--animation` | off | Expose the optional pixel widget on a loopback port. Nothing opens a browser. |
| `--no-animation` | — | Disable the display for this one rally. Mutually exclusive with `--animation`. |
| `--list-players` | — | Print detected players and the auto pick, then exit. |

Both selected players are preflighted before every rally. Use `doctor --players A,B` to check a pair
manually. Each hit tells its agent the remaining count and whether to explore, deepen, or converge.
Those phases scale to the requested rally length at about 30%, 40%, and 30%. A version that exceeds
its phase character budget gets one rewrite attempt; any remaining overage is recorded.

### Owner constraints

Owner non-negotiables become `O-*` ledger entries that players cannot drop. Seed them before the
rally starts. Because the default directory name carries a random suffix, prepare the directory
first instead of guessing it:

```
dir=$(python3 scripts/rally.py setup --idea-file idea.md --constraint "must stay free")
python3 scripts/rally.py --idea-file idea.md -n 10 --out "$dir"
```

`setup` prints only the directory path, so it can be captured directly. Repeat `--constraint` for
each requirement; each one becomes a single bullet in `constraints.md`. With no `--constraint` no
file is written and the rally runs with an empty owner ledger — nothing is inferred into a
requirement. `setup` refuses a directory that already holds a rally or a `constraints.md`, so an
existing rally is never overwritten. You can also write `constraints.md` by hand, one bullet per
line, before starting.

Exit codes: `0` the rally finished, `130` it was cancelled, `1` it ended in an error, `2` the arguments
or player setup were wrong.

### Players

A spec is `kind:name[:model]`. The short version:

- **Agent CLIs** — `cli:claude`, `cli:codex`, or `cli:cursor`, each optionally with `:<model>`. No
  API key needed if you are logged in. Each call runs in a fresh temp directory so the CLI cannot
  touch your repo.
- **Testing** — `mock:left`, `mock:right` return canned replies after a short delay.

These three CLIs are the whole list: there is no API transport and no arbitrary-command player, and
an unsupported spec is rejected before any provider request. Without `--players` the rally is Claude
against Codex; if that pair is not installed, two detected CLIs are used, and with fewer than two the
engine reports the missing CLI rather than substituting a provider. Two sessions of the same CLI are
allowed as an explicit choice. Details are in [PLAYERS.md](ping-pong/PLAYERS.md).

### Following a rally

```sh
python3 scripts/rally.py status --dir D                              # one plain status line
python3 scripts/rally.py wait --dir D --after 0 --timeout 60          # block for the next event
```

`wait` returns one event and prints its ID; pass that ID as the next `--after` to walk the stream in
order. Exit codes: `0` an event arrived, `2` the timeout expired, `1` the rally could not be read.
With no `--after` on a finished rally it reports the terminal event immediately. Both commands fall
back to the active rally when `--dir` is omitted.

Event types include `serve`, `hit`, `fault`, owner `note`, `resume`, and a terminal `done`,
`error`, or `stopped`.

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

The saved preference defaults to on; displaying the widget still requires `--animation`. Changing the preference never interrupts a running rally. A persistent **off** beats a per-run
`--animation` request, so once you turn it off it stays off until you turn it back on. In an embedded
widget, unchecking **Animation** does the same thing and saves the preference. An unreadable or
malformed settings file is treated as off — a broken preference must not force motion on.

### Environment variables

The engine reads no variables of its own. Players are agent CLIs, so they use whatever login the CLI
already has, and provider API keys in the environment are ignored entirely — they affect neither
detection nor selection. To change a model, name it in the spec (`cli:claude:opus`).

### Timeouts and limits

This is fixed in the engine rather than configurable: 1800 s per CLI call.
Recoverable call failures retry once after a five-second delay, then the opponent covers the hit; two consecutive faults stop
the rally. Authentication, unknown-model, and token/context-limit errors stop immediately and are
reported. Interrupted runs can be resumed with the command below.

---

## Files it writes

| Path | What it is |
|---|---|
| `~/.ping-pong/settings.json` | Your persistent `animation` preference |
| `~/.ping-pong/active.json` | Pointer to the most recently started rally, so `status` and `wait` work without `--dir` |
| `<rally dir>/constraints.md` | Owner non-negotiables, one bullet per line, read once when the rally starts |
| `<rally dir>/state.json` | Full rally state, rewritten atomically after every transition |
| `<rally dir>/events.jsonl` | Append-only ordered event log, one JSON object per line |
| `<rally dir>/inbox/` | Owner notes waiting for the next hit, named `note-<sequence>.md` and consumed in submission order |
| `<rally dir>/inbox/consumed/` | Notes already delivered, kept rather than deleted |
| `<rally dir>/engine.lock` | OS lock preventing simultaneous engines for the same rally |
| `<rally dir>/final.md` | The last version plus every open question raised during the rally |
| `<rally dir>/deliverable.md` | Written by the host agent in step 6, not by the engine |

The rally directory defaults to `./.ping-pong/<timestamp>-<slug>-<random>` in your working directory.
`state.json` is always replaced before its event is appended, so a reader may see newer state than the
event it is reading, never older. Your idea and the players' replies stay on your machine; nothing is
uploaded anywhere except to whichever model provider you chose as a player.

During a rally, queue an owner note for the next hit with
`python3 scripts/rally.py note --dir D "text"`. The note remains in each later prompt. Resume an
interrupted or stopped rally with `python3 scripts/rally.py resume --dir D`; completed hits are kept.
Resume refuses to start while another engine holds that rally’s process lock.

---

## Troubleshooting

**"Need exactly two players"** — fewer than two supported CLIs were detected. The message names what
was found and which default CLI is missing. Install a second supported CLI, or pass `--players A,B`
(two sessions of the same CLI are fine). [PLAYERS.md](ping-pong/PLAYERS.md) has setup instructions.

**"Invalid player spec"** — the spec names a kind or CLI that is not supported. Only `cli:claude`,
`cli:codex`, `cli:cursor` and `mock:<name>` exist; API transports were removed.

**Preflight failed** — a selected player could not authenticate, reach its model, or return valid JSON.
Fix the reported issue and start again; the rally has not begun.

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
