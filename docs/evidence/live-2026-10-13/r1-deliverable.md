<!-- Host-written deliverable. The engine's own output is final.md. -->
# ping-pong v2 — ticket-ready spec (host deliverable)

The brief asked for "a ticket-ready spec for the next version of the skill", so
that is the form here: ten vertical slices, each sized to one agent session.
The rally's last version is the body below, kept because it already answered the
requested form; this header carries the owner authority the engine cannot.

**Host flags before you use this.** This rally replayed the *historical* dogfood
brief verbatim for comparison, and that brief predates several owner decisions.
The spec therefore re-proposes work the owner has since cut: the API transports
and the extra CLI players (removed in #21), an adapters/compat table and a cached
doctor probe, a third judge or scoring model, and the host pet. Treat those
slices as historical, not as scope. The slices that remain live are the harness,
persistence, ledger, bounded context, budgets, cancellation, control channel and
resume.

**Standing decisions carried by the rally:** 24 player entries, no owner
constraints were seeded for this run, and no entry was dropped or disputed.

---

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
