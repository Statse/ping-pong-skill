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
- Character budgets: open 1.6x, deepen 1.3x, close 1.0x against the incoming draft,
  plus one non-compounding ceiling of `GROWTH_CEILING` (5) times the served version
  (#6). One rewrite on overage; accept and flag remaining overage. This is not a
  strict size guarantee. A draft already at the ceiling is held, never shrunk.
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
- Players are exactly the three supported agent CLIs (#21): `cli:claude`, `cli:codex`,
  `cli:cursor`, plus the internal `mock:` player for credential-free development. The
  API transports, API-key detection, OpenCode, Copilot, Gemini CLI and the
  arbitrary-command player are removed; `urllib` is no longer imported. The default
  pair is Claude then Codex, falling back to two detected CLIs, and otherwise a report
  naming the missing default CLI and how to choose a pair. No provider substitution,
  no invented model alias, no model enumeration. Two sessions of one CLI remain a valid
  explicit choice. API keys in the environment affect nothing. Covered by
  `tests/test_players.py`.
- `rally.py setup` prepares the rally directory the documented host flow launches with
  (#22). It prints only a fresh directory path, seeds `constraints.md` from repeated
  `--constraint` arguments (one bullet each, newlines collapsed), and refuses a
  directory that already holds a rally or a `constraints.md`. No `--constraint` writes
  no file and the rally runs with an empty owner ledger; nothing is inferred into an
  owner requirement. Starting still accepts `--out`, and the original brief is in every
  hit's prompt. `tests/test_setup_flow.py` runs the documented setup-then-start
  sequence through the real CLI on mock players. Rally directories are built with
  `os.path.abspath` and resolved only after creation: on Windows, `Path.resolve()`
  returned a relative path for a directory that did not exist yet, so the default
  rally directory was printed relative to the launching shell.
- One refined outcome (#12). The owner brief reaches every hit verbatim, labelled as
  carrying any instruction about form, language, audience or length, and the system
  prompt tells players to honor it over their own preferred shape. The host writes one
  `deliverable.md`: the requested form when the brief names one, otherwise a standalone
  refined idea. There is no classification step, template picker, or output interview.
  `final.md` repeats the brief as authoritative, labels a partial rally with its status
  and hit count, and splits the last hit's open questions from questions earlier hits
  stopped asking. The engine never decides a question is answered; the host checks the
  earlier group against the final version, the owner notes and the ledger.
- Contended publishes retry on Windows (#31). See the durability note below.
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
version. #6 is now closed on live evidence (see below). #7 (retry handling) is closed too: the
owner's 2026-10-11 reconciliation superseded its second 20-second delay as conflicting
with one retry, and the implemented behavior - one retry after five seconds, then
opponent coverage - already satisfies it. Do not reopen that delay. The live runs argue
the same way for size rewrites: one rewrite recovered about 10% on a large document, so
a second would not close a 26% gap and would double the slowest hit in the set. The Windows note-ordering CI failure was reproduced locally
with a frozen clock and fixed, and the full matrix (Ubuntu, macOS, Windows on 3.9 and
3.12) is now green on main. #12, #21, #22 and #23 are implemented and merged. #24, #6 and #31 are
implemented on this branch. With those merged, no issue carries unfinished
implementation work: #7 is closed as superseded, #8 stays deferred on measured run
times, and #1 is the umbrella that closes with them. Read
`docs/evidence/live-validation-2026-10-13.md` before touching budgets or the ledger:
it is the live evidence that gated them, and it records what the numbers do not show.

Atomic publishes now survive a concurrent reader (#31). Windows refuses `os.replace`
over a destination another process holds open, so one CI job hit `WinError 5` renaming
`state.json.tmp` over `state.json` while the `wait` CLI was reading it. Every staged
publish - state revisions, the active-rally pointer, and a queued owner note - goes
through `publish()`, which retries `PermissionError` up to 20 times at 50 ms, then
raises one clear error naming the destination and the elapsed bound. The same staged
file is republished each attempt, so a reader still sees a whole revision or the old
one; the event is appended only after the state lands, so a denied publish leaves no
event claiming it happened. Residual limit: a reader that holds the file longer than
the one-second bound still fails the publish, now as a reported engine error rather
than a crash mid-rename.

Four live rallies ran on 2026-10-13 on the default `cli:claude` then `cli:codex` pair
(#24): the historical four-hit dogfood brief, a one-sentence idea over ten hits, a brief
with three seeded `O-*` non-negotiables, and a brief demanding Finnish, under 400 words,
bullets only. All four finished without a fault. Findings, with limitations, are in
`docs/evidence/live-validation-2026-10-13.md`; the older files in `docs/evidence/` remain
the historical baseline. The load-bearing results: players fill the per-hit budget rather
than treat it as a cap, which is why #6 became a ceiling rather than a wider allowance;
the requested form, language and length were honored at every layer; seeded owner entries
plus the conflict report stopped two attempts to design a non-negotiable away; player
ledger entries accumulate toward the 25-entry render cap without consolidating (24 in
four hits, 22 for an 826-character idea), so the next ledger change should be
consolidation or a lower cap for `P-*` only, decided on its own evidence; and `lines_kept`
read 0.0 on hits that demonstrably preserved content, so it measures formatting at these
sizes and is not a retention score. No improvement over the historical baseline is
claimed from one pair of runs. #8 stays deferred: the longest run was 10.6 minutes of
model time and nothing showed existing cancellation to be insufficient. Question triage
(#12) was replaced by the
one-outcome contract above; do not add answered/kept/dropped groups. A players adapter table, cached
probe product, deterministic shape schema, and richer display panels were scope cuts;
do not resurrect them from the old proposal. The API transports and the extra CLI
players are gone (#21); do not reintroduce them, and do not add an adapter registry.

## Validation and agent coordination

Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`.
The suite is 123 credential-free tests: a real four-hit mock rally, event monitoring,
parser fixtures, process cleanup, animation preferences, budgets, note delivery and
durability, resume, and locking; the decision ledger (seeding, cap rendering, disputes,
final output, resume delivery); the lifecycle contracts in `tests/test_lifecycle.py`
(shared error and cancellation policy, exit codes, explicit restore, one per-hit request
policy); player selection in `tests/test_players.py` (detection, default and explicit
pairing, each retained CLI's argv, removed specs); the documented setup-then-start
sequence in `tests/test_setup_flow.py`; and the one-outcome contract in
`tests/test_deliverable.py` (brief carried to every hit, question grouping, partial
rallies, and the host steps in `SKILL.md` and `OUTPUTS.md`).

Each agent needs its own branch and worktree. Give one agent ownership of `rally.py`.
Do not apply the same stash into multiple active worktrees. Integrate one tested slice
at a time; update this handover when implemented scope changes.
