# ping-pong v2: a reliable, watchable idea rally

## Purpose and boundaries

`ping-pong` is an Agent Skill containing a short `SKILL.md`, reference documents, and Python standard-library scripts. The owner supplies an idea and a maximum number of hits. Two selected LLM players alternate: each receives the current version and the previous player's notes, critiques them, and returns a complete improved version. Early hits explore, middle hits make the idea concrete, and late hits converge.

The host agent is the umpire. It selects players, shows progress, relays owner input, and shapes the result into a usable deliverable: a plan or brief, a one-shot build prompt, or a ticket-ready spec in vertical slices.

The signature is a table-tennis court: named paddles, a ball moving toward the active player, hit markers, and a rally log. Every status and statistic comes from engine events. Animation is decorative; it never scores ideas or decides which version wins.

Constraints: Python ≥ 3.9, stdlib only, no package installs, and `SKILL.md` ≤ 100 lines. Installed player CLIs or API credentials are prerequisites. ASCII frames are the baseline; the browser court is available where localhost access works. Native pets are optional.

The skill makes failures visible, preserves owner input in every subsequent prompt, and saves completed work. It does not claim that alternating models proves quality or that preserving a requirement in context guarantees compliance. Live compatibility is demonstrated for specific adapter and CLI versions.

## Package

```text
ping-pong/
  SKILL.md
  reference/
    protocol.md players.md outputs.md display.md troubleshooting.md
  scripts/
    rally.py adapters.py players.json court.py court.html pet.py setup_pet.py
  tests/
    mocks/ fixtures/ test_*.py
```

## Umpire commands

```text
rally.py detect
rally.py doctor --player SPEC [--refresh]
rally.py start --idea FILE -n N [--a SPEC] [--b SPEC]
               [--context FILE] [--owner-notes FILE]
               [--max-minutes M] [--hit-timeout S]
               [--max-estimated-tokens T] [--max-prompt-chars C]
               [--breaks none|phase] [--foreground]
               [--allow-unrestricted SPEC ...]
rally.py wait --after EVENT_ID [--run ID] [--timeout 60]
rally.py status|pause|resume|stop [--run ID]
rally.py answer "text" [--run ID]
rally.py ledger edit|drop O3 ["text"] [--run ID]
rally.py replace --slot a|b --player SPEC [--run ID]
rally.py pick --hit K --reason "..." [--run ID]
```

`N` must be a positive integer; the skill defaults to 6. Omitted `--run` uses `~/.ping-pong/active.json`. That pointer is a convenience; explicit run IDs support concurrent rallies.

`detect` lists installed binaries and credential availability without model calls. It reports adapter capability and whether vendor identity is known. It does not infer that a failed command proves a host sandbox caused it.

`doctor` performs one tiny real round trip and may incur usage. The umpire mentions that before running it. A result records adapter revision, CLI version or API endpoint, requested model, latency, and date. Cache successful results for seven days; changed configuration or `--refresh` requires a new probe. A probe confirms connectivity and response parsing, not full compatibility.

`wait` returns all events newer than `--after`, a new cursor, current status, and an ASCII frame. It returns on available events or emits a heartbeat after the timeout. The umpire starts with cursor 0 and carries the returned cursor forward. Machine-readable output is JSON with the frame as a string.

Exit codes: 0 success, 2 invalid arguments or control, 3 no usable pair, 4 run not found, 5 engine already owns the run.

## Run state and controls

States are `running`, `paused`, `break`, `needs_player`, `interrupted`, and terminal `finished`, `finished_limited`, `stopped`, `failed`.

`start` detaches by default and prints the run ID and court URL. Use a new process session on POSIX and the appropriate detached process flags on Windows. `--foreground` streams events and frames for hosts that do not retain detached children. Host permission restrictions remain in force; the skill uses the host's permitted workflow and reports a limitation when execution is unavailable.

Only one engine owns a run. It holds an OS file lock for its lifetime, using `fcntl` on POSIX or `msvcrt` on Windows. The lock file also records diagnostic PID information; PID existence alone is not lock ownership.

The engine updates a heartbeat every five seconds. If ownership has been released without a terminal commit, `status` and `wait` report `interrupted`. A stale heartbeat with a held lock reports an unresponsive engine and does not permit a second engine to start.

Controls are written as unique, atomically published request files. The engine assigns event sequence numbers when it accepts them and acknowledges applied or rejected controls. A successful command means the request was queued; `wait` or `status` confirms application. Terminal runs reject controls except candidate selection.

- `answer` creates a persistent owner entry at the next hit boundary.
- `ledger edit|drop` changes an owner entry only on explicit owner instruction.
- `pause` finishes the current call within its timeout, then starts no new calls.
- `resume` continues paused, break, interrupted, or repaired `needs_player` runs.
- `replace` changes a slot only while paused or awaiting a player; the adapter must pass the same eligibility rules as initial selection. Replacement does not resume automatically.
- `stop` immediately prevents new calls and cancels the active local work. CLI process groups receive TERM, followed after five seconds by forced termination; Windows uses tree termination. API requests run in a terminable worker process. Remote API processing or billing may continue after local cancellation.
- `pick` records an earlier valid hit as the final candidate with a reason. It does not change the version used for subsequent hits. Otherwise the final candidate is the latest valid hit.

`resume` retains completed hits and the original phase schedule. An unfinished provider call can be repeated and is labeled as a possible duplicate. Exactly-once billing is not promised.

## Hit protocol

A plays odd numbered hits and B plays even numbered hits. A fallback may make one player return twice consecutively; the log records this. A hit advances only after a valid response is committed.

Phase schedule:

- N = 1: converge.
- N = 2: open, converge.
- N ≥ 3: open and converge each receive `max(1, floor(N/3))` hits; concretize receives the remainder.

Thus N = 4 gives 1/2/1 and N = 7 gives 2/3/2. Open challenges assumptions and explores alternatives. Concretize supplies behavior, boundaries, edge cases, and acceptance criteria. Converge resolves contradictions, cuts repetition, and exposes remaining blockers. No automatic early stopping in v2; the owner can stop at any time.

Each prompt contains, in order:

1. Protocol instructions, phase, hit number, response schema, and the requirement to return the complete version.
2. The original idea verbatim.
3. Active owner entries.
4. Optional context brief.
5. Current version, initially the original idea.
6. Previous critique and changes.
7. Outstanding questions.

Source text is delimited as data. These delimiters organize the prompt; they are not a security boundary. Preserve the language of the original idea.

The original idea is capped at 12,000 characters and context at 8,000. Oversized input is rejected before starting; the umpire may prepare a shorter brief for owner approval. The assembled prompt cap defaults to 60,000 characters. If exceeded during a run, enter `break` with the cause. Never silently truncate. An optional higher cap can be supplied on resume; completed prompts remain unchanged.

Response:

```json
{
  "critique": "honest, specific notes",
  "version": "the complete improved idea",
  "changes": ["one short line per change"],
  "open_questions": [
    {"q": "question only the owner can answer", "blocking": true}
  ]
}
```

`critique`, `version`, and `changes` are required and type-checked. `open_questions` defaults to an empty list; strings are accepted as nonblocking questions. Unknown fields are ignored. The parser accepts plain JSON, one fenced object, or a single unambiguous object surrounded by prose.

An empty version or explicit whole-document placeholders such as “rest unchanged” causes repair. A large reduction in length produces a visible warning, not rejection: cutting is part of convergence. The umpire verifies completeness when shaping.

Questions are deduplicated by normalized exact text. Players may refer to existing question IDs as resolved; resolution is recorded, and the umpire checks it against owner answers. Unresolved questions remain in the artifacts.

## Failures and limits

Each scheduled hit has one retry or repair allowance in total for its original player. If that attempt also fails, the opponent gets one fallback attempt using the same semantic input. There is no retry on the fallback. If both players fail that hit, end as `failed` with the last valid version.

| Failure | Action |
|---|---|
| Invalid JSON or schema | One repair with the validation error |
| Timeout, 429, 5xx, or retryable transport failure | One retry after five seconds, if limits allow |
| Authentication failure, missing binary, known unsupported flag | Disable that adapter for this run; try the healthy opponent |
| No eligible player remains | Enter `needs_player` |
| Unclassified CLI failure | Report diagnostic and consume the normal retry allowance |

Repairs use the original hit input plus the validation error. Invalid output is logged but never becomes current state. `let` marks a retry or repair; `net` marks a failed attempt. Every actual provider invocation is logged, including doctor, retry, repair, and fallback.

Defaults: hit timeout 300 seconds and active-run budget 45 minutes. Count running time, including retries and backoff; exclude deliberate paused, break, and needs-player time and downtime after interruption. Persist accumulated elapsed time and use a monotonic clock within each engine session. Restarting cannot reset limits.

Before each call, cap its timeout to the remaining budget. Do not start a call with less than 60 seconds remaining; an in-flight call ends when its capped timeout expires. Exhaustion produces `finished_limited`, with the phase reached and unfinished work visible. No extra convergence call follows.

`--max-estimated-tokens` is an optional stopping threshold based on cumulative prompt and output characters divided by four. Display it with `≈`. Check it before each call; a response can overshoot it. It is neither a hard token cap nor a monetary budget. Record provider-reported usage separately and report unknown usage honestly.

## Preserve owner intent

Keep a single owner ledger in v2. The umpire seeds at most 15 one-line `O#` entries from the owner's stated requirements and shows them in the serve message. This is not an additional approval gate. Owner corrections and answers persist as entries; initial and later entries are always included in subsequent prompts.

Players cannot edit this ledger. They explain conflicts in their critique or questions. Only explicit owner instructions authorize editing or dropping an entry. Keep the original idea verbatim even when the umpire omits a seed ledger.

Player proposal ledgers, merge operations, and automatic convergence declarations are deferred. The complete version and immutable changes already preserve proposal history; a second mutable ledger adds bookkeeping without verifying requirement compliance.

During shaping, the umpire marks each active owner entry honored, disputed, or unclear, with a short reason. An omitted requirement is repaired in the deliverable or surfaced as unresolved. Compliance is a semantic review, not a schema guarantee.

With `--breaks phase`, pause after the open and concretize groups when unresolved blocking questions exist: at most two automatic breaks. The owner may answer or instruct the umpire to play on. Resume is explicit; silence never means approval. Default breaks to `none` in the engine; the interactive skill passes `phase`.

## Players

Keep adapters in `players.json`, with small handlers in `adapters.py`. Support the existing spec families: `cli:claude`, `cli:codex`, `cli:cursor`, `cli:opencode`, `cli:copilot`, `cli:gemini`, provider/model API specs, and `mock:name`.

Each adapter declares executable, argument array, input and output transport, requested model options, restrictive mode, revision, and tested versions. Commands use `subprocess` without a shell and run in a temporary directory outside the owner's repo. Remove other providers' known API credentials from the child environment. This directory and environment filtering are not a sandbox.

Automatic selection excludes adapters without a verified tool-free or read-only mode. The owner may explicitly opt into a named unrestricted adapter. Do not invent or silently substitute unsupported restrictive flags.

Select owner overrides first, then a probe-passed pair with known different vendors, then eligible detected players with known different vendors, then any eligible pair with a visible vendor-uncertainty notice. Multi-model CLIs and routing providers have unknown vendor identity unless trusted configuration identifies the model provider. Requested and reported model identifiers are shown separately; model self-description is not evidence.

Release acceptance requires opt-in end-to-end smoke tests for Claude Code and Codex, recording CLI versions and successful complete rallies. Other adapters remain experimental until equivalent tests pass. Host and player support tables are separate. Windows remains experimental until the platform tests pass.

## Display and artifacts

The engine serves the browser court on a random `127.0.0.1` port. Only `GET /` and `GET /state.json` are supported. The page polls every second. Insert all model text through `textContent`; embedded replay data must also be safely encoded. No model content is executed or rendered as active HTML.

Show paddles with player and vendor, active-player ball, phase, completed-hit dots, retry and fault badges, log, owner ledger, questions, status banners, and candidate copy button. Respect reduced-motion preferences. If polling fails, show “connection lost”; the browser cannot assert that a dead engine is still running. Resuming prints a fresh court URL.

Display-only shot names use `1 - difflib.SequenceMatcher(...).ratio()` against the previous version: smash above 50%, drive from 10% through 50%, push below 10%. These describe textual change, not quality. Event commentary stays factual: “Codex drives back: 4 reported changes, 1 blocking question.”

`wait` returns ASCII frames on transitions and heartbeats. The umpire posts meaningful transitions and no more than one heartbeat frame per minute. A missing browser never blocks a rally.

Use a unique run ID and output directory `.ping-pong/<timestamp>-<slug>-<suffix>/`. Save:

- `original.md`, optional `context.md`, and owner ledger history.
- `state.json`, a derived snapshot written with temporary file plus `os.replace`.
- Immutable event records and `hits/NNN-<player>.json` containing raw and parsed output, prompt hash, timing, and usage.
- `calls.jsonl`, recording call start and outcome, including uncertain calls after interruption.
- `final.md`, `deliverable.md`, and a self-contained offline `replay.html`.

Immutable committed events and hits are the recovery authority; state is rebuilt from them. Commit hit content before its completion event, then update state. Ignore uncommitted hit files on recovery. A crash between these writes must not advance or duplicate a completed hit.

`final.md` is engine-generated: candidate, owner entries, questions, diagnostics, usage, and a match card with hits, lets, nets, clean streak, duration, and calls. Before the first valid hit, use the original idea as the labeled starting candidate. `deliverable.md` contains the umpire's shaped result and compliance review. The distinction prevents the engine from overwriting agent-authored shaping.

Offer to ignore `.ping-pong/` on the first repo run; do not modify `.gitignore` without authorization. Raw artifacts may contain the supplied idea and player output.

## Shape the result

Templates live in `reference/outputs.md`.

- Non-code: choose the most usable plan, pitch, or brief and explain the choice.
- One-shot build prompt: use only for one repo, a credible single-session scope, no migrations or infrastructure/account setup, no unresolved blockers, and locally verifiable acceptance. Include scope, interfaces, acceptance criteria, and verification commands.
- Larger code: produce independently demonstrable vertical slices with dependencies, boundaries, acceptance criteria, and verification, ready for `/to-tickets` or `/to-issues`.

Explain the choice in two or three sentences. Keep blockers and partial-run limitations visible. Shaping does not build the code or publish issues unless the owner also requests that work.

## SKILL.md flow

1. Parse idea, hit count, and overrides.
2. Detect players, select a pair, and probe uncached selections with usage disclosed.
3. Seed owner entries and optional context without automatically collecting repo files or secrets.
4. Start the rally; share court URL and frame. Offer native pet setup once where supported.
5. Wait with the event cursor; relay owner input and handle breaks, failures, and limits.
6. Shape the candidate and review owner requirements.
7. Report deliverable path, decisions, unresolved questions, compatibility, and usage limitations.

## Ticket-ready delivery slices

1. **Watchable mock rally.** Engine, response parsing, phases, event cursor, immutable commits, ASCII court, browser court, final artifact, and replay. Demo a four-hit mock rally. Verify phases for N = 1…9, no advancement on malformed or placeholder output, legitimate short rewrites, inert hostile text, and no missing or repeated events after cursor reuse.
2. **A tested live pair.** Claude and Codex adapters, restrictive modes, doctor, invocation logs, retry/fallback policy, and replacement. Verify exact tested CLI versions, fallback with the same semantic input, disabled authentication failures, and a complete rally using both players.
3. **Owner input survives.** Ledger seed/edit/drop, persistent answers, question tracking, and phase breaks. Verify each answer appears in every later prompt, only owner controls mutate entries, silence leaves breaks paused, and conflicts survive into artifacts.
4. **Interrupt and recover.** Exclusive lock, queued controls, active-time budget, estimated-token threshold, process cancellation, and resume. Inject crashes at each commit boundary; verify completed hits survive once, abandoned calls are labeled uncertain, a held lock prevents a second engine, paused time is excluded, and stop starts no further calls.
5. **Useful deliverables.** Candidate selection, output templates, separate shaping artifact, compliance review, and factual match card. Review reference cases for a non-code brief, small CLI tool, and multi-service feature; verify blockers remain visible and replay works without networking.
6. **Broader compatibility and optional pets.** Add remaining CLIs and APIs incrementally, each with experimental status and opt-in smoke tests. Test Windows detach, locks, termination, and quoting before claiming support. Claude statusline wraps the existing command; Cursor footer replacement requires explicit opt-in; OpenCode toasts occur only on hit, fault, break, and finish, at most once per 20 seconds. Back up configuration and use hash-guarded uninstall; failed pet setup never blocks a rally.

Mocks cover malformed output, placeholders, short valid convergence, timeout, authentication failure, retries, and interrupted calls. Fixtures cover parser boundaries; live tests establish compatibility. Each slice ships a demonstrable user path.

---

Rally: 4 hits between Claude Code and Codex.

Open questions raised during the rally:
- Is the host pet a must-have, or can it slip to a later version if time is short?
- What N do you expect typically (4? 10?), and what cost or time per rally is acceptable?
- Should rallies ever work on existing codebases (so the context brief is needed), or are ideas always greenfield?
- Is an optional third-model judge worth it, or is cross-scoring enough for you?
- Which hosts matter most for v2 testing? Is Windows in scope now or later?
- Should the user be able to choose 'keep last' instead of 'keep best', e.g. for creative ideas where scores mislead?
- Which two player CLIs and operating system should receive verified support first?
- Should early stopping be enabled by default, or should the requested N normally be played in full?
- When only same-provider or unknown-provider players are available, should automatic selection proceed with a visible label or require an explicit choice?
- Should owner controls in the browser ship in the first release, or can CLI and host-chat controls cover the initial version?
- Is v2 primarily for greenfield ideas, or must refining ideas against an existing codebase be a first-release capability?
- What default elapsed-time and per-hit timeout limits fit the rallies you expect to run?
- Which live pair should be certified first: claude + codex as proposed, or one that matches your own daily hosts?
- Should phase breaks be on by default in interactive hosts, or should the rally always run uninterrupted unless you pass --breaks?
- Is deferring browser controls (court stays read-only, control goes through chat) acceptable for v2?
- Should run artifacts live in the repo's .ping-pong/ (gitignored) or under ~/.ping-pong/ to avoid touching the user's repo at all?
- Is Python 3.9 an acceptable minimum, and is Windows a v2 requirement or a stretch goal?
- Should the default N be 6, and is a 45-minute default wall-clock limit right for your typical ideas?
- Do you want an explicit privacy notice before the first serve, since the idea and context are sent to third-party providers?
