# Project review: return to two-model idea refinement

Reviewed 2026-10-13 against the current checkout, HANDOVER.md, SPEC-v2.md, shipped skill, engine, display, tests, packaging, CI and recorded live evidence. This is a whole-project review, not a branch-diff review. Recommendations below propose scope changes; they do not supersede the accepted spec or authorize deleting features.

Follow-up: the user subsequently authorized fixes for correctness findings 1–4. Those fixes and regression tests are now implemented; see HANDOVER.md. The findings below describe the reviewed baseline. The broader removal recommendations have not been implemented.

## Second review of the fixes

The 10 targeted regression tests pass. Additional deterministic, credential-free
probes found two remaining gaps; neither was changed during this second review:

1. **P1 — concurrent note allocation can silently lose a submitted note.**
   `append_note()` calculates the next sequence before exclusively claiming its inbox
   filename (`rally.py:1090`). If another writer claims that sequence and the engine
   consumes/archives it before the delayed writer claims it, the inbox name is free
   again. The delayed writer reuses an already-consumed identity; `consume_notes()`
   treats the new text as already delivered, and `archive_note()` deletes it because
   the archive destination exists. A deterministic interleaving delivered and archived
   only the first publisher's text, despite both submissions reporting success.
   Sequence allocation and reservation need a concurrency-safe guarantee across both
   pending and consumed identities. The new tests interleave after reservation, so
   they miss this earlier race. This is a pre-existing gap beyond the fixed overtaking
   case, but it prevents claiming concurrent note delivery is fully safe.
2. **P2 — stdout content still influences fatal classification.**
   Removing argv fixes the reported prompt leak, but `_cli()` still falls back to
   stdout as its diagnostic (`rally.py:148`). A CLI exiting 1 with empty stderr and
   partial model output `Draft: an API key management tool` is classified as fatal,
   bypassing retry. Separate model output from transport diagnostics and classify
   only reliable error information. The regression fixtures always supply a clean
   stderr error, so they do not cover this remaining path.

No further defect was identified in the direct question/conflict handoff or the
new field-type validation. These review results do not supersede the passing full
suite of 133 tests; they identify cases absent from that suite.

## Verdict

The original mechanism still exists: two configured model endpoints take turns improving the current draft. The product around it has become a miniature workflow system. Renaming `Player` helps, but the larger issue is asking models to maintain a decision database and asking the host to reconstruct a separate final result.

Suggested product contract:

> Bounce an idea between two models for a chosen number of turns. Each model critiques and improves the previous draft while preserving your instructions. Return the refined idea and any unresolved questions.

Keep the ping-pong name. Use ordinary language in instructions and progress: model, turn, draft, refinement, user instructions. There is no scoring, winner or referee decision in the engine.

## Terminology and conceptual accuracy

| Existing term | Suggested term | Reason |
| --- | --- | --- |
| Player | Model endpoint internally; model in user copy | `Player` wraps a CLI and optional model selection; it is not a competing participant. |
| Opponent / against / vs | Other model / with | Both calls cooperate on one result. |
| Hit / serve | Turn / first draft | Makes the requested count immediately understandable. |
| Rally | Refinement run in technical descriptions | The brand can retain the metaphor without requiring its vocabulary everywhere. |
| Umpire | Host assistant | The host launches, checks and presents work; no judging mechanism exists. |
| Owner / owner non-negotiables | User / requirements | Avoids introducing another role to describe the person asking. |
| Fault / opponent covers | Failed turn / retry or stop | Describes actual behavior and makes deviations from alternation visible. |

`Player` is a reasonable small boundary for invoking different CLIs. Rename it rather than replacing it with a provider registry or several abstraction layers. Sources: `ping-pong/scripts/rally.py:52`, `:122`, `:206`; `ping-pong/SKILL.md:8`.

The engine launches a fresh CLI process in a fresh directory for every call. These are two configured endpoints, not two persistent conversations with independent remembered histories. Also, `cli:claude` and `cli:codex` identify tools; their effective models depend on each CLI's defaults unless explicitly supplied. Keep the distinction clear without adding model-catalog discovery.

## Removal and simplification inventory

These are product judgments, not claims that the existing implementation violated its scope. Many features were explicitly requested in the current spec.

| Priority | Item | Recommendation and tradeoff | Relevant source |
| --- | --- | --- | --- |
| First | Competitive vocabulary | Replace player, opponent, umpire and hit in the primary experience. Keep the project name. | `README.md:12`; `ping-pong/SKILL.md:8`; engine prompt |
| First | Model-authored `P-*` ledger | Remove add/drop operations, IDs, standing/dropped status, refusal records, rendering caps and dedicated ledger events for model decisions. Let the draft carry the model's decisions. This sacrifices a structured decision audit, so compare requirement retention on recorded briefs before shipping. | `rally.py:346`, `:421`, `:902`, `:959`, `:1188` |
| First | `O-*` IDs and owner ledger machinery | Preserve user requirements as persistent text, along with a simple conflict report. Numeric IDs and drop rejection are unnecessary if models cannot edit requirements in the first place. Retaining a requirement in metadata alone does not enforce it in prose. | `rally.py:274`, `:360`, `:911` |
| First | Mandatory constraint extraction and setup command | Accept explicit requirements on the start command, or rely on the complete brief where appropriate. Create the run directory once and report it. Remove the host's setup-then-start ceremony and separately seeded `constraints.md` once replacement behavior is tested. | `rally.py:308`, `:324`; skill step 3 |
| First | Host rewriting after the final model turn | Make the final model draft the canonical result; have the host check requirements and present it. If correction is needed, make it explicit. Current synthesis is a third editorial stage that can expand or change the two-model result. | skill steps 5–6; `OUTPUTS.md`; `rally.py:1115` |
| First | Two competing final artifacts | Expose one result file. Keep diagnostics and transcript separately. Today `final.md` is an annotated engine result while `deliverable.md` is a different host-written result. | `rally.py:1115`; skill step 6 |
| First | Output template catalog and ticket handoff | Replace `OUTPUTS.md` with a short rule: honor the requested format, otherwise return a standalone refined idea. Remove the automatic `/to-tickets` offer. Plans/specs remain valid when requested; they need no built-in template family. | `OUTPUTS.md`; skill step 7 |
| First | Line-retention metric and drift wording | Remove `lines_kept` from user progress and quality claims; preferably retire its calculation. Keep size information only if useful for length control. Verbatim line matching does not measure preserved meaning. | `rally.py:439`, `:459`; `README.md:183` |
| First | Decorative display subsystem | Remove or distribute separately: `animation.py`, all three widget assets, `DISPLAY.md`, animation flags/commands, global settings, display tests and integration code. It adds a threaded HTTP server and a browser lifecycle without improving the idea. A branding preference can justify keeping it, but it is not core. | `ping-pong/scripts/animation.py`; `ping-pong/assets/`; `rally.py:1214`, `:1281` |
| First | Historical host animation integration proposals | Archive the support research and pixel-animation checks away from active product guidance if the display is removed. Do not implement the proposed native adapters. | `docs/host-animation-support.md`; `docs/evidence/pixel-animation-checks.md` |
| Next | Mandatory remote preflight on every start and resume | Consider making remote probes diagnostic-only. Local executable/configuration checks plus a useful first turn avoid two extra model requests per run. Tradeoff: the second endpoint can fail after the first has done work; preserve partial results. Current preflight is explicitly scoped, so this is a proposed change, not a defect. | `rally.py:633`, `:655`, `:1100`, `:1270` |
| Next | Silent coverage by the other endpoint after failure | Prefer one retry followed by a clear partial result. Current fallback can produce consecutive drafts from the same endpoint, weakening the two-model contract. Keep only if continuity is more important than strict alternation. | `rally.py:820` |
| Next | Global active-run pointer | Prefer explicit run paths in host calls and remove `~/.ping-pong/active.json` convenience if unused. The documented host flow already knows the directory. Removes global mutable selection across projects. | `rally.py:36`, `:526`, `:561` |
| Next | Historical question aggregation as an output layer | Once open questions are actually forwarded between turns, let the final turn return the unresolved set and retain previous questions in the transcript. Avoid exact-string grouping plus a host reconciliation pass. Do not remove this before fixing the missing handoff described below. | `rally.py:1155`; skill step 6 |
| Next | Seven-step workflow as an invariant | Preserve the under-100-line constraint, but drop the requirement that there must be exactly seven steps. A concise start–follow–present flow is sufficient after the cuts above. | `SPEC-v2.md:20`; `tests/test_deliverable.py:141` |
| Next | Repeated status and historical scope documentation | Make SPEC-v2 the present contract, HANDOVER a short operational handoff and README the user guide. Move recovery narratives and completed-issue histories out of the everyday reading path. The spec still labels the completed ledger as “Next slice.” Preserve recovery references and evidence. | `HANDOVER.md`; `SPEC-v2.md:85`; `README.md` |
| Small | Mock random sleeps | Remove the 2.5–5 second random sleep by default; use an explicit delay fixture only for process/monitoring tests. It adds latency and timing variability to credential-free checks. | `rally.py:183`; `tests/test_rally.py:341` |
| Small | Thin helpers and theatrical progress method names | `Progress.fly/land` and `remaining_iterations()` do not need elaborate abstractions. Inline trivial calculations or use plain progress names when touching the affected code. These are cleanup, not the central problem. | `rally.py:248`, `:675` |
| Small | Tests that freeze implementation wording | Remove or replace tests of seven numbered steps, exact prose and removed private helpers when simplifying. Keep behavioral coverage. The extra match-keyword scan duplicates the Python 3.9 AST check; CI also runs compatibility tests separately and again in the full suite. | `tests/test_deliverable.py:130`; `tests/test_compatibility.py:49`; `.github/workflows/` |

The clearest evidence for removing model ledger bookkeeping is R2: 22 standing model decisions for an 826-character final draft; six entries repeat the midnight-lock rule. R1 had 24 standing model entries after four turns, almost at the 25-entry prompt cap. Source: `docs/evidence/live-validation-2026-10-13.md`, confirmed against archived state JSON. These observations support simplification; they do not prove that removing all requirement reminders preserves quality.

## Correctness findings

### 1. Open questions and requirement conflicts are not passed to the next model

`user_prompt()` (`rally.py:381`) passes the brief, notes, ledger, draft, critique and changes, but omits the prior reply's `open_questions` and `owner_conflicts`. Anything expressed only in those fields is unavailable to the next model. It is collected again for the host at the end, creating repair work after the refinement loop.

Confirmed with sentinel questions and conflicts in a prior reply: neither sentinel appears in the next prompt. Forward unresolved questions and conflicts explicitly; do not depend on incidental duplication in the draft.

### 2. Note ordering breaks when an earlier claimed file is still empty

`consume_notes()` (`rally.py:997`, especially `:1014`) skips an empty reserved note and continues consuming later ones. Reserve note 1, publish note 2, consume, then publish note 1: persistent owner notes become `['Second', 'First']`. This contradicts the claimed submission-order guarantee. The suite tests an empty reservation alone, not an empty reservation followed by a ready note.

If retaining live notes, stop at an unpublished earlier reservation and define recovery for abandoned reservations. Do not remove atomic publication or deduplication merely to shrink code.

### 3. Prompt content can turn a transient CLI failure into a fatal error

`_cli()` includes the complete command, including the prompt, in its error string (`rally.py:142`). `is_fatal_player_error()` scans the entire string (`:887`). A transient failure on an idea about “API key management” therefore matches `api key` and stops immediately instead of retrying.

Confirmed by passing the resulting error shape to the classifier. Classify the actual transport diagnostic separately from command/prompt text. Avoid duplicating the full brief and draft into fault logs.

### 4. The JSON parser accepts malformed versions as successful drafts

`parse_reply()` (`rally.py:397`) coerces any truthy `version` to a string and iterates non-list fields. `{"version":{"bad":"shape"}}` is accepted as a Python dictionary string; `{"version":"ok","changes":"abc"}` becomes three changes, `a`, `b`, `c`.

Confirmed locally. Validate a nonempty string draft and appropriate collection types. A small strict envelope is useful; the ledger mutation protocol is the unnecessary part.

### 5. Documentation promises more than the implementation establishes

- `README.md:183` calls line retention an honest refinement measure. Later live evidence explicitly says it measures reflow and is not usable as retention evidence.
- `PLAYERS.md:15` and the README say a temporary working directory means CLIs cannot touch the repository. Changing cwd is not an access-control boundary; the launcher does not establish that guarantee. Say “runs outside the repository” and describe only actual restrictions.
- “Until it is sharp” in the README implies a quality stopping condition. The engine executes a fixed count with no judge or convergence test. Say “for the requested number of turns.”

## What should stay

- Two configurable endpoints, including two explicitly selected models through the same CLI; the existing three CLI implementations and internal mock are a modest scope.
- The complete user brief on every turn, persistent requirements, and visible conflicts.
- The current draft, concise critique, changes and unresolved questions passed forward in a small validated envelope.
- A chosen turn count and lightweight explore/deepen/converge guidance. These are directly relevant to refinement.
- Length control. The live evidence demonstrates growth and weak rewrites; replacing it with no bound would repeat a known problem. Evaluate simpler limits separately, rather than adding tolerances or more retries.
- A saved transcript/checkpoint, atomic writes, cancellation, child-process cleanup, clear errors and partial output.
- Resume and a single-writer lock if resume remains supported. Several minutes of model work are worth preserving.
- Basic status/wait monitoring for host tool timeouts. Remove redundant ledger events, not the whole monitoring mechanism without a replacement.
- Live user notes if steering an ongoing run remains part of the intended experience. Their durability code is necessary for that promise; legacy filename compatibility is removable only with an explicit migration/support decision.
- Standard-library-only Python 3.9 compatibility, packaging, meaningful credential-free tests and the existing platform CI. More than one operating system is not itself product bloat.
- Historical live artifacts and recovery references as evidence. Archive or de-emphasize them; do not destroy them to make the tree look smaller.

## Standards and validation

The current engine is 1,307 lines and the display server is another 109, plus 135 lines of browser assets. The skill is 40 lines, satisfying its length constraint. No dependency or Python-floor violation was identified in this review.

Possible divergent-change smell: `rally.py` owns CLI invocation, prompt design, ledger operations, durable notes, process lifecycle, monitoring and artifact rendering. Cut unnecessary features first; only then consider a small separation between model invocation and the refinement loop. Splitting the existing complexity into many modules would not solve the product problem.

Ran `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`: **123 tests passed in 51.174 seconds**. Additional credential-free probes confirmed findings 1–4 above. No new live provider calls were made. Passing tests establish the existing covered behavior, not outcome quality or coverage of the identified gaps. Recorded live results are historical evidence, not rerun results.

## Suggested order

1. Agree on the short product contract and vocabulary; correct misleading claims.
2. Fix the missing question/conflict handoff and response/error validation.
3. Remove model ledger operations, fold requirements into start, and return one canonical result. Compare saved briefs and requirements before accepting the behavioral change.
4. Remove the display subsystem, output templates and historical product proposals from the active workflow.
5. Reassess remote preflight, failure coverage and global active-run convenience independently.
6. Update the spec and handover when implementation scope is actually changed; retain recovery and evidence records.

At the time of the review, only this document was added. Subsequent authorized fixes are recorded in the follow-up note above.
