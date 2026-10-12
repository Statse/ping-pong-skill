# Handover: recovered baseline

Updated 2026-10-07. Start here, then read `SPEC-v2.md` for scope and acceptance criteria.
This replaces the stale handover that described already-committed work as uncommitted.

## Baseline and current owner decisions

`/ping-pong 10 <idea>` means ten total alternating hits between two independent agent
sessions, normally five each. Default is 10; `-n` overrides it. Both players may use the
same CLI. The host writes `deliverable.md` using judgment and `ping-pong/OUTPUTS.md`.

The newest decisions recorded in the recovered refine worktree supersede the old v2
proposal: scaled 30/40/30 phases, per-phase character budgets with one rewrite attempt,
persistent owner notes, resume, immediate stops for fatal context/setup errors, and
small preflight calls. These are now implemented with credential-free regression tests.
Preflight is automatic; do not run doctor first unless a separate diagnostic is useful.

Display: two small pixel paddles and one ball, decorative only. It stops on completion,
error, cancellation, or disconnection. Persistent off wins over `--animation`; reduced
motion is respected. Native host adapters remain deferred. See `ping-pong/DISPLAY.md`.

## Implemented and verified locally

- Atomic state writes followed by ordered append-only events; plain `status` and `wait`.
- Drift metrics `lines_kept` and `size_ratio` on each hit (null on the serve).
- Default 10 hits, phase-scaled prompts, and remaining-hit count.
- Character budgets: open 1.6x, deepen 1.3x, close 1.0x. One rewrite on overage;
  accept and flag remaining overage. This is not a strict size guarantee.
- Unparsed replies are faults. One retry after five seconds, with a JSON reminder;
  opponent covers the hit after failure. Two consecutive faults stop the rally.
- Fatal token/context, authentication, model, and missing-tool errors stop immediately.
- Both selected players receive a small format preflight before starting or resuming.
- Owner notes are queued in `inbox/` as `note-<9-digit sequence>.md`. The claimed
  filename, not a timestamp, fixes submission order, so a coarse Windows clock can no
  longer reverse two quick notes. A note's identity is committed in the same state
  revision as its text and kept in `consumed_notes`, so an interruption between the
  commit and the file move cannot deliver it twice; delivered files move to
  `inbox/consumed/` instead of being deleted. Identity, not text, is deduplicated, so
  two identical notes are both kept. A reserved but still empty file is left for a
  later hit. Legacy `note-<timestamp>-<random>.md` files in older rallies are still
  consumed once, ordered before current-format notes. Notes are retained in
  subsequent prompts and `final.md`; multiline notes are preserved.
- Durable decision ledger (#5). State carries `ledger` entries
  `{id, by, text, status, reason}` and a `disputes` list. `constraints.md` in the rally
  directory seeds `O-1`, `O-2`, … owner non-negotiables, one bullet per non-empty line;
  a missing or empty file yields an empty owner ledger. Player replies may send
  `decisions: [{op, id?, text?, reason?}]`; junk items and unknown ops are ignored.
  Every prompt renders the ledger, capped at 25 rendered entries by evicting the oldest
  player entries only, with an explicit cap-exception line when owner entries overflow.
  Eviction is rendering-only; state keeps everything. Refused and rejected operations
  (owner drops, reasonless drops, unknown or already-dropped ids, text-less adds) become
  disputes and never fault or end the rally. A hit's ledger changes are written into the
  same atomic state revision as the hit itself, so a crash cannot keep a completed hit
  while losing its decisions; the separate `ledger` event is appended afterwards, once
  per hit that changed anything. Resume preserves the stored ledger and does not re-seed it.
  `final.md` lists standing decisions, dropped ones with reasons, and disputes;
  `status` reports the standing count.
- Unified lifecycle (#23). `execute()` is the one execution path for a new and a
  resumed rally: it starts the rally if needed, runs the turns, and applies one
  cancellation/error/finalization policy, so both paths end in a terminal state with a
  usable `final.md` even before the first completed hit. `conclude()` writes every
  terminal state, `report_result()` prints status and maps the exit code (done 0,
  stopped 130, anything else 1), and `terminate_as_cancel()` turns SIGTERM into a
  cancellation. `Rally.load()` replaced the `__new__` hack as the supported restore
  path; it defaults missing collections and never re-seeds the ledger. `fetch_reply()`
  owns the per-hit request policy (one JSON retry, one size rewrite, no retry when
  fatal) and the loop owns alternation and committing. An engine error is recorded on
  the rally and in `final.md` instead of being raised past the caller. The unused
  per-hit duration average and the `expected_s` progress argument are gone; per-hit
  elapsed seconds are still recorded and printed.
- Owner notes are published into their claimed inbox name atomically, so a note queued
  while the engine reads the inbox is delivered whole or waits for the next hit.
- Resume keeps completed hits and event IDs. An OS lock prevents simultaneous engines
  writing the same rally. OS locks release automatically when an engine exits or dies.
- Cancellation and faults leave a usable `final.md`, even before the first completed hit.
- Stdlib-only Python 3.9 floor. Windows remains best-effort pending a live rally.

## Recovery record

The original mixed work is preserved, not discarded:

- `recovery/refine-2026-10-07`: snapshot of the dirty refine worktree.
- `recovery/stash-2026-10-07`: durable reference to the original stash commit.
- Original `stash@{0}` remains available.
- Patch copies: `<git-common-dir>/recovery-2026-10-07/refine.patch` and `stash.patch`.

The failure was an incomplete reconciliation: `play_turns()` called a missing
`size_budget()` and passed owner notes to a three-argument `user_prompt()`. Both missing
implementations were recovered from the stash. Regression tests now exercise the actual
rally flow, not just the helper functions.

The original refine worktree is now clean on `recovery/refine-2026-10-07`, preserving
its historical WIP as a commit. Continue from the recovery
branch or merged main; do not resume implementation from that stale worktree.

## Remaining work and limits

#5 (decision ledger) is implemented and tested in `tests/test_ledger.py`. #11 (owner
notes) is now implemented: the owner's rewritten issue scopes it to exactly-once
delivery and ordering, and explicitly rules out automatic note-to-ledger conversion and
phase pauses, so `O-*` entries still come from `constraints.md` only. The ledger records
and reports lost requirements; it still does not force a player to keep text in its
version. #6 (budgets) and #7 (retry handling) remain partial; keep their remaining
acceptance criteria explicit. The second retry delay mentioned in #7 requires resolving
its conflict with one retry. The Windows note-ordering CI failure was reproduced locally
with a frozen clock and fixed, but the cross-platform matrix must be confirmed on CI.
Issues #12, #21, #22, #23, and #24 carry newer owner decisions than this handover's
earlier scope notes; read them before picking the next slice.

No paid live dogfood rally was run during recovery. Keep `docs/evidence/` as the historical
baseline; a live rerun is required to demonstrate improved retention and convergence.
Time budgets and final question triage remain planned. A players adapter table, cached
probe product, deterministic shape schema, and richer display panels were scope cuts;
do not resurrect them from the old proposal. Existing API/extra CLI transports remain
supported until a dedicated cleanup is explicitly chosen.

## Validation and agent coordination

Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`.
The suite includes a real four-hit mock rally, event monitoring, parser fixtures,
process cleanup, animation preferences, budgets, note delivery and durability,
resume, locking, and the decision ledger (seeding, cap rendering, disputes, final output, resume delivery),
and the lifecycle contracts in `tests/test_lifecycle.py` (shared error and cancellation
policy, exit codes, explicit restore, and the single per-hit request policy).

Each agent needs its own branch and worktree. Give one agent ownership of `rally.py`.
Do not apply the same stash into multiple active worktrees. Integrate one tested slice
at a time; update this handover when implemented scope changes.
