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
- Retain current API and extra CLI transports pending a separately chosen cleanup.
- Display is an optional decorative pixel loop under #16. No scores, court panels,
  replay, automatic external browser, or host configuration installers.
- macOS/Linux are the local target; Windows is best-effort through credential-free CI.

## Architecture

`ping-pong/scripts/rally.py` owns players, prompts, state, events, monitoring, notes,
resume, and final artifacts. `animation.py` owns the optional loopback widget and its
persistent preference. `assets/` contains the host-neutral component and local adapter.

`state.json` is replaced atomically before the matching event is appended to
`events.jsonl`. Each rally has an OS-held `engine.lock` to prevent competing writers.
Owner notes are queued as timestamped files under `inbox/`, consumed in submission
order, and retained in state. The host produces `deliverable.md` separately.

## Recovered engine acceptance

Implemented and tested without credentials:

- A default mock rally completes ten hits; explicit `-n` changes the count.
- Every player sees the phase, remaining count, and character limit.
- Budget multipliers are open 1.6x / deepen 1.3x / close 1.0x of incoming length.
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

- **Length budgets (#6): partial.** Current limits and one rewrite are tested. A `let`
  event, any revised tolerance, and paid live acceptance measurements remain outstanding.
  Current behavior retries an overage in any phase; it does not guarantee convergence.
- **Retry handling (#7): partial.** Unparsed faults, a JSON reminder, and one five-second
  backoff are implemented. The issue also mentions a 20-second delay while allowing
  only one retry; resolve this before changing retry count or closing the issue.
- **Wall-clock budget (#8): planned.** Bound elapsed time and stop with a partial artifact.
- **Owner inbox (#11): partial.** Persistent prompt notes and `note` exist. Converting
  answers into `O-*` ledger entries depends on #5. The recovered implementation uses
  atomic files under `inbox/`, replacing the old single-file inbox proposal.
- **Question triage (#12): planned.** Final questions need answered / kept / dropped
  groups with reasons and deduplication. Current output collects all raised questions.
- **Native animation adapters (#16): deferred.** Keep host-neutral behavior and current
  embedding claims accurate. Research in `docs/host-animation-support.md` is historical.

## Live validation

After ledger and length-budget work, rerun the recorded four-hit dogfood idea with
Claude/Codex and store evidence under `docs/evidence/`. Compare median line retention
with the 0–1% baseline and compare final length with hit 3. A second eight-hit run should
inform multiplier defaults. Do not claim measured improvement from mock tests.

## Scope cuts

Do not revive these closed proposals without a new owner request: `players.json`
adapter product (#9), version-keyed doctor cache and model enumeration (#10),
deterministic shape metadata (#13), court panels (#14), or a protocol-document rewrite
(#15). Small preflight calls were reinstated by the latest recorded owner decisions;
the broader diagnostics product remains out of scope.

No new player transports, judge model, replay UI, convergence stopping, cost table,
or guaranteed live Windows support.
