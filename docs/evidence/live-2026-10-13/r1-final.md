# ping-pong v2: ticket-ready spec

## Goal and constraints
An Agent Skill that rallies an idea between two different LLMs. Each hit critiques the incoming version and rewrites it. Early hits explore, middle hits deepen, late hits converge. The host agent acts as umpire and turns the selected result into a usable non-code document, a one-shot build prompt, or a ticket-ready spec in vertical slices.

Python stdlib only; no dependency installs; SKILL.md ≤100 lines. Keep the side-view ping-pong court as the signature element. Preserve players `cli:claude|codex|cursor|opencode|copilot|gemini`, `anthropic:<model>`, `openai:<model>`, `gemini:<model>`, `openrouter:<model>` and offline `mock:<name>`. Installed player CLIs and API credentials are prerequisites. GUI hosts use the scripts wherever shell access exists; unavailable hooks fall back to court and chat frames.

Fixed layout: `SKILL.md`, `OUTPUTS.md`, `adapters.json`, `compat.json`, `schema.json`, `scripts/{rally,players,court,pet,setup_pet}.py`, `tests/`. No script exceeds 800 lines. Features without offline tests are experimental and off by default; real-service compatibility also requires real smoke tests. Each ticket must fit one agent session. S/M are estimates; split oversized slices at their stated seams before ticketing, without deleting required behavior.

## Commands and artifacts
`rally.py start --idea FILE --hits N [--players A,B] [--max-minutes M] [--max-requests R] [--per-hit-timeout 300] [--ask] [--no-final-score] [--no-early-stop] [--allow-same-vendor] [--allow-unverified-pair]`

Also: `status [run] [--json]`, `say [run] stop|pause|resume|note|answer ...`, `resume [run]`, `doctor [--probe]`, `frame [run]`. `run` defaults to `~/.ping-pong/active.json`. `say answer Q-3 --require "…"` creates an owner requirement. Positive hits and limits are required. Unset total budgets are shown explicitly.

Exit codes: 0 completed or command queued; 2 invalid args/no eligible pair; 3 paused, stopped or budget exhausted; 4 fault limit; 5 runner lock held. Queuing a command is distinct from its acknowledgement in state. `status --json` reports lifecycle and acknowledgement status.

Each `.ping-pong/<timestamp>-<slug>/` holds `state.json`, `inbox.jsonl`, `final.md`, `court.html`, `replay.html`, and eventually host-authored `deliverable.md`. State records schema version, brief, player identities, accepted versions, attempts, ledger epochs, answers, questions, scores, command acknowledgements, budgets, lifecycle and selection reason. Write the active pointer atomically too.

## Protocol and owner authority
Each hit receives the original brief verbatim, latest accepted version, opponent notes, active O-*/P-* ledger, binding owner context, open Q-* questions, phase, version cap and remaining limits. Best-version selection does not change the version passed to the next hit.

Reply example:
```json
{"critique":"…","version":"…","changes":["…"],
 "open_questions":[{"text":"…"}],"closes":[{"id":"Q-2","reason":"…"}],
 "owner_conflicts":[{"item":"O-1","reason":"…"}],
 "decisions":[{"op":"add","text":"…","evidence":"excerpt"},
              {"op":"drop","id":"P-3","reason":"…"}],
 "score_in":{"fidelity":8,"clarity":7,"completeness":6,"feasibility":8},
 "requirements_check":{"O-1":"excerpt","P-9":"excerpt"},
 "done":false,"shape":null}
```

Validate types, bounds, references and ledger operations; assign new P-* and Q-* IDs only on acceptance. Every retained O-* and declared touched P-* needs an excerpt ≤200 characters from `version`, matched after deterministic whitespace/markdown normalisation, or a referenced explicit conflict. New decisions use inline `evidence`; drops use their required reason. Mechanical checks cannot detect undeclared semantic changes: the host reviews those and spot-checks untouched entries. Validation proves structure and excerpt presence, not requirement fidelity.

Players cannot drop O-* entries. P-* drops require reasons. Unresolved O-conflicts block a ready-to-build label. Answers become binding A-* context; `--require` creates O-* instead. Owner notes also bind later requests. Only explicit owner input naming an O-* or A-* ID can supersede it; preserve history and identify supersessions alongside the original brief. Never infer repeal from a casual remark. Q-* questions persist until answered or closed with a reason and remain visible in final artifacts.

Phases: one hit = converge; two = deepen, converge. For N≥3, explore gets `floor(N/3)` hits, deepen gets `floor(N/3)`, converge gets the remainder. Caps: explore 12k, deepen 14k, converge 10k characters. Converge adds no major scope. If the complete request context exceeds 60k characters, pause and explain; never silently truncate owner content.

A hit slot has at most three attempts: scheduled player, one retry with the error, one opponent fallback. Invalid output, timeout and provider failure are faults. Two consecutive slots exhausting all attempts stop the rally; acceptance resets this counter. Failures do not consume accepted hits. Disclose broken alternation. Stop, pause, total-budget exhaustion and superseded replies are not faults.

## S1 — Offline harness, persistence, minimal court (M)
Implement mock players and a two-hit rally with a working table, paddles, ball and state display. Every later slice extends this harness.

Write state through a same-directory temporary file, flush/fsync and atomic replacement. The exclusive runner lock records PID and process identity where available. Break it only when its process is demonstrably gone; uncertainty returns 5. The court never owns this lock. Commit each accepted hit and ledger changes together. Resume may reissue an uncommitted request, incurring another charge, but cannot duplicate an accepted hit.

Acceptance: network-free `python -m unittest` completes in <30s. Fixtures cover malformed replies, supported envelopes, timeout, retry/fallback and crash recovery. Interrupted writes leave readable state; a second runner exits 5.

## S2 — Ledger, questions, bounded context (S)
Implement protocol validation, owner authority, historical versions and context caps. `schema.json` defines formats, normalisation and rubric anchors; enforce them with stdlib code, without a JSON Schema dependency.

Acceptance: a six-hit fixture preserves owner requirements. Illegal drops, missing declared coverage and unmatched excerpts trigger retry; whitespace differences pass. Additions receive IDs after validation; drops require reasons rather than fabricated excerpts. Supersession stays auditable. Decisions and questions appear in final artifacts and replay.

## S3 — Adapters and doctor (M; seam: CLI/API)
Adapter example, illustrating format rather than claimed compatibility:
```json
{"id":"cli:codex","rev":3,"exe":"codex",
 "argv":["exec","--output-last-message","{out}","{prompt}"],
 "alt_argv":[],"output":"file","version":["--version"],
 "provider":"openai","model_flag":"--model"}
```
Run argument arrays without a shell in a temp directory; disable tools where supported. Document that a temp directory is not a sandbox. Prefer supported stdin/file prompts when argument limits matter. Shared parsers handle text, JSON and JSONL envelopes; unusual adapters use small named functions. Reject unexplained prose around JSON.

API transports use stdlib HTTP with finite timeouts. Blocking calls run in cancellable worker processes so controls and deadlines remain responsive for all players. API cancellation ends local waiting; remote computation or billing may continue. CLI cancellation targets the process tree.

`doctor` reports executable/version, configured model/provider evidence and credential presence without secrets. `--probe` sends a tiny potentially billed JSON request; SKILL.md discloses this before invocation. Cache for seven days by executable path/version or API endpoint, adapter revision, model and routing configuration. Failed probes are excluded from auto-pick; unprobed players are labelled unverified. Preserve `PING_PONG_MODEL_<VENDOR>` overrides. `compat.json` records exact real-service smoke-tested identities, dates and outcomes; compatibility claims cover only those configurations.

Acceptance: report identity, cache age, status and latency. Offline tests cover envelopes, fallback flags and identity invalidation. API mocks demonstrate cancellation and deadlines.

## S4 — Honest diversity (S)
Record host executable, model ID, underlying provider and evidence separately. Use configuration or reliable metadata, never player self-description. OpenRouter is transport; undisclosed routing remains unknown.

Auto-pick prefers verified different providers. Same-provider pairs require `--allow-same-vendor`; unknown pairs require `--allow-unverified-pair`. Persist warnings on the court. Reject an identical known model pair; neither override makes identical models different LLMs. If no pair qualifies, list options and exit 2.

Acceptance: Cursor configured for Anthropic plus Claude is flagged as same-provider; unknown metadata is never verified; identical known models are rejected.

## S5 — Scoring, selection, convergence (M; seam: selection/early stop)
No third judge. Players score the incoming candidate 1–10 on fidelity, clarity, completeness and feasibility. Criterion-specific anchors live in `schema.json`: 1 fundamental failure, 5 usable with major gaps, 10 ready for its requested purpose. Store scorer, candidate and epoch IDs. Peer ratings are opinions, not measurements.

A ledger change or new binding owner input starts an epoch. Scores of incoming versions belong to the context under which they were evaluated, not to the subsequent rewrite. Within the current epoch, select the highest mean score; prefer the latest scored candidate if within 1.0 of the best. Host requirement review is required before delivery. Older epochs cannot win.

After the last accepted hit, make one bounded score-only request to its opponent under current context. It returns candidate/epoch reference, scores and conflicts, without rewrite or ledger edits. It counts as a request, not a hit; `--no-final-score` disables it. On failure or omission, choose the best scored current-epoch candidate. If none exists, present the latest accepted version as unscored for host review. Never borrow a predecessor's score. Record selection and whether final scoring failed or was skipped.

Early stop requires ≥3 accepted hits, two consecutive normalised `difflib` ratios >0.95, no epoch changes across those comparisons, no unresolved O-conflicts, and `done:true` from both players on their latest accepted turns in that epoch. Similarity alone cannot stop play.

Acceptance: fixtures cover outdated winners, last-hit ledger changes, missing/failed final scores, formatting-only similarity and only one player declaring done.

## S6 — Budgets and cancellation (S)
Optional `--max-minutes` and `--max-requests`; `--per-hit-timeout` defaults to 300s. Count all dispatched generation and scoring requests, including retries/fallbacks. Doctor probes are separate and reported. Persist active elapsed time across resume, excluding pauses and runner downtime.

Enforce deadlines during calls. Per-hit timeout faults the attempt; total-budget exhaustion cancels it, writes partial artifacts and exits 3. Terminate CLI process groups on POSIX and trees with `taskkill /T` on Windows; report any termination limitation. Show provider usage when supplied, otherwise label chars/4 as an estimate. Opaque subscriptions have no guaranteed dollar accounting.

Acceptance: request/time budgets stop blocked mocks with valid partial output; per-hit timeout follows retry policy; pause time is excluded. Windows support claims require real platform checks.

## S7 — Control channel and resume (M; seam: inbox/recovery)
Inbox example:
```json
{"id":"c-…","ts":"…","cmd":"answer","q":"Q-3","text":"…","require":false}
```
Commands are stop, pause, resume, answer and note. `say`, court controls and host relays use one locked append writer. Commit acknowledgements with their state effects; repeated IDs have no effect. Ignore an incomplete trailing line until completed; report malformed complete lines.

Poll at least every second during calls. Stop cancels the attempt and finalises partial output. Pause cancels it, keeps the hit queued, commits paused state and exits 3, releasing the lock. `resume` acquires the lock, appends/processes resume and continues with the same players. `say resume` queues intent only; the host must invoke `resume` to launch an exited runner. The court explains this distinction.

Notes/answers queue durably without immediately cancelling paid work. If binding context changes during a call, retain its reply as a superseded attempt, reject its version/ledger edits and repeat the hit with updated context. Count the request, not a fault. Drain pending commands before accepting a reply or finalising selection; never commit a reply against stale binding context.

`--ask` pauses after explore, or before the final hit if there is no explore phase, and shows open questions. Resume without answers is allowed; the checkpoint fires once.

Acceptance: stop interrupts a blocked mock within 2s; duplicates are harmless; crash/resume preserves acknowledgements and numbering; mid-call owner input cannot produce stale acceptance; one-hit `--ask` pauses once.

## S8 — Deliverable rules (S)
Converge replies include `shape: {kind, est_files, est_sessions, unknowns[], rationale}`. Use each player's latest current-epoch estimate; combine code estimates with maxima and the union of blocking unknowns. Missing either estimate defaults code to slices.

Rules: non-code when implementation is not requested; one-shot when sessions ≤1, files ≤10, no blocking unknowns and no unresolved O-conflicts; otherwise vertical slices. Explicit owner form/language wins. The host may override classification with a recorded reason.

`final.md` contains selected idea, provenance, ledger, conflicts and questions. After fidelity review, the host writes separate `deliverable.md` using `OUTPUTS.md`: usable non-code document, one-shot prompt, or slices with goal, scope, dependencies, size and acceptance criteria, ready for `/to-tickets` or `/to-issues`. Conflicts and blocking unknowns remain visible and prevent a ready-to-build label.

Acceptance: fixtures cover conflicting/missing estimates, owner-input invalidation and owner format overrides. Tests verify classification, not host editorial judgment.

## S9 — Court and replay (M)
Extend S1 with scoreboard, hit dots, rally log, copy button, phase, thinking/retrying/paused states, budget meters and selection provenance. The ball travels toward the active player. Recorded-data fun only: ace for score gain ≥2, let for retry, net fault for failed attempt, paddle flash for a new decision, deuce for scores within 0.5, final match card with hits, aces, faults, decisions and selected version. Compare ratings only within an epoch; omit ace/deuce and rating-winner claims without comparable scores. Label peer ratings and respect reduced motion.

Bind to 127.0.0.1; serve only run artifacts. Control POSTs require a per-run token, exact Origin and validated Host. Escape user/model content; do not render executable HTML. Offline replay embeds snapshots, has no token, controls or network dependency, and works over `file://`. Print the URL if browser opening fails. `frame` prints the ASCII court; host pastes it about once a minute in every UI.

Acceptance: updates within 2s; offline replay works; injected script/markdown cannot execute; unauthorised controls and path traversal fail; unsupported comparisons produce no rating events.

## S10 — Host pet (S; seam: statusline/OpenCode)
Offer once: Claude Code statusline with `refreshInterval: 1` where verified; Cursor opt-in with footer-replacement warning; OpenCode toasts only at hit/match end. Others use court/frames. Claude Code is the preferred default tier, with installation offered rather than silent config edits. Hooks remain experimental/off by default until smoke-tested.

`setup_pet.py` wraps existing statuslines, backs up config, supports `--dry-run`/`--uninstall`. Restore original bytes only if config is unchanged since install; otherwise remove owned values only when they still match installation, or report a conflict. Preserve subsequent user edits. Use `sys.executable`, `pathlib` and host-specific tested quoting.

Acceptance: offline fixtures preserve later edits; real macOS/Linux checks precede support claims; Windows waits for verified checks.

## Delivery
Build S1→S10, splitting at declared seams when necessary. Every slice extends the working offline harness. SKILL.md keeps seven steps: read args → doctor/select → start background rally → show court/offer pet once → poll, relay input and paste frames → review/select/shape deliverable → report artifacts, conflicts and next action. Supporting files hold formats, rubric, adapters and templates.

Out of scope: third judge, parallel rallies, GUI-specific pets and guaranteed subscription spend accounting.

---

Rally: 4/4 hits between Claude Code and Codex.

Owner brief (authoritative, as given):

# Idea to refine: the "ping-pong" agent skill

## What it is
`ping-pong` is an Agent Skill (a folder with SKILL.md + scripts) for coding agents: Claude Code, Codex CLI, Cursor CLI and OpenCode, plus their GUI versions. The user gives an **idea** and a number of **iterations**. The skill bounces the idea between two different LLMs. Each **hit** means one model gets the current version and its opponent's notes, critiques them, and returns an improved version. Early hits open the idea up, middle hits make it concrete, and late hits converge. The agent running the skill acts as umpire: it starts the rally, shows its progress, and turns the final version into a deliverable:
- **Non-code idea** → whatever form is most usable (plan, pitch, brief…).
- **Code that one agent session can build** → a one-shot build prompt.
- **Larger code** → a ticket-ready spec in vertical slices, so `/to-tickets` or `/to-issues` can split it.

## How it works now
- `scripts/rally.py` (Python stdlib only) runs the rally.
  - Players are specs like `cli:claude`, `cli:codex`, `cli:cursor`, `cli:opencode`, `cli:copilot`, `cli:gemini`, `anthropic:<model>`, `openai:<model>`, `gemini:<model>`, `openrouter:<model>`, or `mock:<name>`.
  - It auto-detects available CLIs and API keys and prefers two different vendors.
  - Each player must reply with JSON: `critique`, `version`, `changes`, `open_questions`.
  - CLIs run in a temp dir, away from the user's repo.
  - On a failure the player gets one retry, then the opponent takes the hit. Two faults in a row stop the rally.
  - Outputs go to `.ping-pong/<timestamp>-<slug>/`: `state.json` (updated after every hit), `final.md`, and `replay.html`. A pointer is written to `~/.ping-pong/active.json`.
- **Display**, in three layers:
  1. **Live court**: `court.html` is served on localhost and opened in the browser. It shows a side-view table tennis table with two paddles; the ball flies toward whichever model is thinking. It also has a scoreboard, a progress dot per hit, a rally log, the final version with a copy button, and an offline replay.
  2. **Chat frames**: `pet.py --frame` prints a small ASCII court. The agent pastes it about once a minute while polling. This works in every UI.
  3. **Pet in the agent's own UI** (inspired by the Copilot desk pet), installed with `setup_pet.py`:
     - Claude Code: a statusline line with an animated ball (`refreshInterval: 1`).
     - Cursor CLI: a statusline line; it replaces the native footer while installed.
     - OpenCode: a plugin that shows toasts.
     - Codex, Copilot CLI and all GUI versions: no hook available, so no pet.
     The installer wraps any existing statusline, backs up config, and supports `--uninstall`.
- `SKILL.md` gives the agent 7 steps: take args → pick players → start the rally in the background → show the rally (offer the pet once) → check the rally → shape the deliverable (`OUTPUTS.md` templates) → report.

## Known weak spots / open questions
- I haven't tested it against real CLIs. Headless flags change often (`agent -p --mode ask`, `opencode run`, `copilot -s -p`, `codex exec --output-last-message`), and the default API model names may be stale.
- The rally is purely sequential with no judge. Is alternating critique+rewrite the best protocol? Alternatives: a third "umpire" model scoring each hit, early stopping when versions converge, or keeping the best version rather than the last.
- Context grows only with the latest version plus notes, so earlier good ideas can be silently dropped across many hits.
- Several cursor-agent/opencode/copilot players may run the same underlying vendor, so "different LLMs" isn't guaranteed.
- The pet is uneven across hosts: Cursor replaces its own footer, and OpenCode toasts can be spammy or easy to miss.
- The deliverable classification (one-shot vs tickets) is a judgment made by the umpire agent. Should the players vote, or should there be measurable criteria?
- There's no cost or time budget, no cancel or resume, and no way for the user to interject mid-rally (e.g. answer open questions between hits).
- Windows support is untested (shlex quoting in statusline commands, `python3` vs `python`).

## What I want from the refinement
Make the skill more reliable, more useful and more fun, while keeping it simple: stdlib Python, no installs, and SKILL.md under ~100 lines. Keep the ping-pong visual as the signature element. The end product should be a ticket-ready spec for the next version of the skill.

Size limit retries that remained over budget: 2, 4.

Questions raised earlier that the last hit no longer asks. Check the final version, the owner notes and the ledger before relisting them; do not invent answers:
- Should the final deliverable default to the best-scored version or always the last one?
- Is a pause for user answers after the open-up phase (--ask) wanted by default, or only on request?
- Which hosts matter most if pet effort must be cut: Claude Code only?
- Should a ledger violation count as a fault (retry, then lose the hit) or just a warning?
- Is CI (e.g. GitHub Actions on 3 OSes) available for this repo?
- Which real CLI versions must pass smoke tests for the initial v2 release?
- What default total request and time limits should a new rally use?
- Should the final score-only request stay on by default, given it adds one billed request per run?
- Which host CLIs must have real smoke tests in compat.json before v2 is released (minimum set)?
- Is Windows parity required for v2, or acceptable as a later follow-up once it's verified?
- Should owner answers become non-negotiable (O-*) by default, or stay as A-* context unless marked --require?
- What default number of hits should the skill use when the user doesn't give one?

Status: done.

Decisions standing at the end of the rally:
- P-1 (Claude Code): P-1: A decision ledger (O-* owner, P-* player) is passed every hit and validated by rally.py
- P-2 (Claude Code): P-2: CLI adapters live in adapters.json and are verified by `rally.py doctor`, with cached results
- P-3 (Claude Code): P-3: No third judge model by default; players score incoming versions, the best version is kept, and the rally stops early on convergence
- P-4 (Claude Code): P-4: A file-based inbox (inbox.jsonl) is the single mechanism for stop, pause, resume and interjection
- P-5 (Claude Code): P-5: Deliverable shape is decided by an explicit rule over player-reported estimates, and the umpire may override with a stated reason
- P-6 (Claude Code): P-6: The court is the main fun surface; the pet is tiered (Claude Code default, Cursor opt-in, OpenCode throttled)
- P-7 (Claude Code): P-7: Deliverable is a ticket-ready spec in vertical slices, each with acceptance criteria, built test-harness first
- P-8 (Codex): P-8: Ledger coverage uses supporting excerpts and host semantic review; automated validation does not claim to prove requirement fidelity.
- P-9 (Codex): P-9: Provider diversity requires configuration or reliable metadata; unknown pairs need an explicit override.
- P-10 (Codex): P-10: Durable state is atomic, runners are exclusive, and inbox commands are acknowledged idempotently; controls are polled during calls.
- P-11 (Codex): P-11: Final scoring is a bounded score-only request; ledger changes invalidate old comparisons, and convergence needs both players' agreement.
- P-12 (Codex): P-12: Doctor caches by execution identity and adapter revision; claimed compatibility requires real smoke tests.
- P-13 (Codex): P-13: Court controls are authenticated on loopback, replay is inert, and pet uninstall preserves subsequent user edits.
- P-14 (Claude Code): P-14: Simplicity budget — fixed file layout, no script over 800 lines, every slice sized to one agent session, and features without offline tests are off by default
- P-15 (Claude Code): P-15: rally.py exposes start/status/say/resume/doctor/frame with defined exit codes; reply, adapter and inbox formats are given by concrete examples
- P-16 (Claude Code): P-16: requirements_check covers all O-* plus P-* entries touched this hit, using whitespace/markdown-normalised excerpts of ≤200 chars; other entries are spot-checked by the host (refines P-8)
- P-17 (Claude Code): P-17: A minimal court ships in S1; court fun features (ace, let, fault, deuce, match card) come only from recorded data, with no extra model calls
- P-18 (Claude Code): P-18: Owner answers are A-* binding context by default and become O-* only when marked --require
- P-19 (Codex): P-19: New decisions provide inline evidence before ID assignment; drops provide reasons. Host review detects undeclared semantic changes.
- P-20 (Codex): P-20: Binding owner input supersedes in-flight replies; spent requests remain recorded, and the same hit repeats under updated context.
- P-21 (Codex): P-21: Missing final scores select the best scored current-epoch candidate, or expose the latest version as unscored; predecessor scores are never inherited.
- P-22 (Codex): P-22: All player calls use cancellable workers; API cancellation stops local waiting without promising remote cancellation or avoiding charges.
- P-23 (Codex): P-23: Paused runners exit and release their lock; say resume queues intent, while resume launches continuation.
- P-24 (Codex): P-24: Identical known model pairs are rejected; diversity overrides cover same-provider or unknown pairs only.
