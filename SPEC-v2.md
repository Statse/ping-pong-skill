# Spec: ping-pong v2

Current scope, reconciled 2026-10-07. `HANDOVER.md` records implementation and recovery
status. This document supersedes the original proposal; earlier versions remain in Git.
The latest owner decisions recorded in the refine worktree govern conflicting older
issue text. GitHub issues remain the tracker, not evidence that a feature is complete.

## Problem and goal

The historical four-hit Claude/Codex rally completed without faults, but grew from
4.5 KB to 20.2 KB while retaining only 0–1% of substantial lines per hit. The final hit
also dropped its open questions. See `docs/evidence/` for raw measurements.

The goal is to refine while preserving requirements, limit growth, report failures,
and let the owner contribute without losing completed work.

## Constraints and current decisions

- Python 3.9+, standard library only, no dependency installation.
- `ping-pong/SKILL.md` stays under 100 lines and retains the seven-step host workflow.
- Default 10 total alternating hits; `-n` overrides it. The last completed version wins.
- Two independent agent sessions may use the same CLI. No judge or early stopping.
- Explore/deepen/converge phases scale roughly 30%/40%/30%; prompts include remaining hits.
- Keep the JSON envelope. Unparsed replies must not become a version.
- Use one per-phase size rewrite and flag any remaining overage.
- Owner notes persist; interrupted rallies can resume.
- Fatal context/token or setup errors stop immediately with a usable partial artifact.
- Preflight the selected pair with small format calls. A cache/model-enumeration product
  is deferred; automatic preflight does not require a separate doctor invocation.
- The host chooses the final output using `OUTPUTS.md`, without a shape schema or vote.
- Players are only the Claude, Codex and Cursor CLIs, defaulting to Claude then Codex,
  plus the internal mock. The API transports and extra CLI players were removed in #21;
  this supersedes the earlier decision to retain them.
- Display is an optional decorative pixel loop under #16. No scores, court panels,
  replay, automatic external browser, or host configuration installers.
- macOS/Linux are the local target; Windows is best-effort through credential-free CI.

## Architecture

`ping-pong/scripts/rally.py` owns players, prompts, state, events, monitoring, notes,
resume, and final artifacts. Its `setup` subcommand prepares a known fresh rally
directory and seeds `constraints.md`, so the documented host flow never guesses a
generated directory name. `animation.py` owns the optional loopback widget and its
persistent preference. `assets/` contains the host-neutral component and local adapter.

`state.json` is replaced atomically before the matching event is appended to
`events.jsonl`. Each rally has an OS-held `engine.lock` to prevent competing writers.
Owner notes are queued under `inbox/` as `note-<sequence>.md`, where the claimed
filename and not a clock fixes submission order. A note's identity is committed with
its text, so an interruption cannot deliver it twice; delivered files move to
`inbox/consumed/`. A note's text is published into its claimed name atomically, so the
engine never reads a half-written note. The host produces `deliverable.md` separately.

Starting and resuming share one lifecycle: `execute()` runs the remaining turns under a
single cancellation, error, and finalization policy, `conclude()` writes the terminal
state, `report_result()` prints the status and maps the exit code, and `Rally.load()` is
the supported way to restore saved state. `fetch_reply()` owns the whole per-hit request
policy — one JSON retry, one size rewrite, no retry for a fatal error — while the turn
loop owns alternation and committing hits.

## Recovered engine acceptance

Implemented and tested without credentials:

- A default mock rally completes ten hits; explicit `-n` changes the count.
- Every player sees the phase, remaining count, and character limit.
- Budget multipliers are open 1.6x / deepen 1.3x / close 1.0x of incoming length,
  bounded by one non-compounding ceiling of five times the served version, so the
  allowance cannot ratchet with the hit count. A draft already at the ceiling is held
  at its current length rather than asked to shrink.
  The first draft uses at least 120 input characters as its budget base.
- An oversized version gets exactly one rewrite attempt. Remaining overage is flagged
  in state and in `final.md`; size repair does not count as a player fault.
- Unparsed output gets one retry with a JSON-only reminder after five seconds. If that
  fails, record a fault and let the opponent cover the hit. Two consecutive faults stop.
- Fatal errors skip retry and stop; `final.md` includes the cause and completed work.
- Failed preflight leaves no half-created rally directory.
- Notes submitted during a hit enter the following prompt and all later prompts,
  preserve submission order and multiline content, and are consumed once.
- Resume keeps completed hit numbering and sides, appends ordered event IDs, and
  preserves owner notes. It refuses to compete with an active engine.
- Drift telemetry remains available on every hit, with null metrics on the serve.
- Animation and process cleanup tests remain green.

## Next slice: durable decision ledger (#5)

The next feature addresses preservation directly. Depends on the existing events and
prompt flow, not on a new display.

- Add `ledger` entries `{id, by, text, status, reason}`. `O-*` entries are owner
  non-negotiables; `P-*` entries are player decisions.
- Seed from `constraints.md` in the rally directory when present, one bullet per line.
  A missing file is valid and creates an empty owner ledger.
- Include the full compact ledger in every prompt. Cap at 25 entries by evicting oldest
  player entries first; never evict owner entries. An owner-only overflow must preserve
  every owner entry and make the cap exception explicit.
- Extend the reply with `decisions: [{op: "add"|"drop", id?, text?, reason?}]`.
- Reject a drop without a reason. Refuse owner-entry drops and record a dispute.
- `final.md` shows standing decisions and disputes without losing undropped decisions.

Acceptance:

- A scripted player trying to drop `O-1` is refused; the rally continues and the dispute
  appears in both state and final output.
- A drop without a reason is rejected and reported.
- A 40-entry fixture proves owner entries are never evicted.
- Captured prompts prove the ledger reaches every player.
- A rally without constraints runs with an empty owner ledger.
- Final output retains every decision that was not dropped.

## Remaining slices

- **Length budgets (#6): done.** Phase limits, one rewrite, and a non-compounding
  ceiling of five times the served version are implemented and tested, and the live
  measurements that set that number are in `docs/evidence/live-validation-2026-10-13.md`.
  Live players fill the allowance rather than treat it as a cap, so the ceiling - not a
  wider tolerance - is what prevents runaway growth. Behavior still retries an overage
  in any phase and still does not guarantee convergence; a `let` event was not added.
- **Retry handling (#7): done.** Unparsed faults, a JSON reminder, and one five-second
  backoff are implemented and tested. The issue's second 20-second delay was superseded
  by the owner's 2026-10-11 reconciliation as conflicting with one retry; the issue is
  closed. Do not reintroduce a second retry delay without a new owner request.
- **Lifecycle unification (#23): implemented.** New and resumed runs share one
  execution and finalization path, a loaded rally has an explicit constructor, the
  per-hit request policy is one operation, and the unused duration average is gone.
  Externally observable behavior is unchanged except that `final.md` now names an
  engine error. Tested in `tests/test_lifecycle.py`.
- **Wall-clock budget (#8): deferred on evidence.** The live runs' longest rally was
  10.6 minutes of model time, with a 282-second worst hit, and existing cancellation
  already leaves a usable artifact. Add a timer only if a future run shows otherwise.
- **Owner inbox (#11): done.** Persistent prompt notes, `note`, sequence-ordered
  queueing, and exactly-once delivery across interruption and resume are implemented.
  The owner decision rules out automatic note-to-ledger conversion and phase pauses;
  `O-*` entries come from `constraints.md` only.
- **Supported players (#21): done.** Three CLIs, the mock, and no API transports.
- **Documented constraint flow (#22): done.** `setup` prints a fresh directory and
  seeds explicit owner constraints; starting uses `--out` with that directory.
- **One refined outcome (#12): implemented.** `/ping-pong "idea"` returns one outcome.
  An explicit form, language, audience or length in the brief wins; without one the host
  writes a standalone refined idea. The brief reaches every hit verbatim and the system
  prompt tells players to honor it. `final.md` repeats the brief, marks a partial rally,
  and splits the last hit's open questions from ones it stopped asking; the engine never
  declares a question answered. No answered/kept/dropped schema and no template picker
  were added, replacing the old question-triage proposal.
- **Native animation adapters (#16): deferred.** Keep host-neutral behavior and current
  embedding claims accurate. Research in `docs/host-animation-support.md` is historical.

## Live validation

Done on 2026-10-13 (#24): four rallies on `cli:claude` then `cli:codex` - the recorded
four-hit dogfood idea, a one-sentence idea over ten hits, a brief with three seeded
`O-*` non-negotiables, and a brief demanding Finnish, under 400 words, bullets only.
Results and limitations are in `docs/evidence/live-validation-2026-10-13.md`; the older
files there remain the historical baseline.

Line retention was dropped as a quality measure rather than compared: `lines_kept` read
0.0 on hits whose own changes preserved every decision, so at these document sizes it
measures reflowing, not retention. Semantic preservation was judged by reading the
outputs. No measured improvement over the baseline is claimed from one pair of runs, and
nothing here was concluded from mock tests.

## Scope cuts

Do not revive these closed proposals without a new owner request: `players.json`
adapter product (#9), version-keyed doctor cache and model enumeration (#10),
deterministic shape metadata (#13), court panels (#14), or a protocol-document rewrite
(#15). Small preflight calls were reinstated by the latest recorded owner decisions;
the broader diagnostics product remains out of scope.

No new player transports, judge model, replay UI, convergence stopping, cost table,
or guaranteed live Windows support.
