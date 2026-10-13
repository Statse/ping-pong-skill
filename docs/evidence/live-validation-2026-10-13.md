# Live outcome-quality validation (#24) — 2026-10-13

Pre-registered before any provider request was sent. Results are appended below
after the runs; nothing in the selection was chosen after seeing an outcome.

## Environment

- Engine: this branch (`publish()` retry for #31 included). Python 3.9.6, stdlib only.
- Players: `cli:claude` (Claude Code 2.1.291) serving, `cli:codex` (codex-cli 0.160.0)
  returning. This is the engine's default pair; no model alias is chosen by the engine,
  so the effective model is each CLI's own default for this account.
- Rally directories under `/tmp/pp-live/.ping-pong/`, outside the repo. Each run's
  raw artifacts are archived in `live-2026-10-13/`: `<run>-state.json` (every hit,
  critique, ledger entry and budget), the engine's `<run>-final.md`, the host-written
  `<run>-deliverable.md`, and R3's seeded `r3-constraints.md`. Every number below is
  recomputable from those files.

## Selected runs

| Run | Brief | Chars in | Hits | Constraints | What it tests |
|-----|-------|----------|------|-------------|---------------|
| R1 | historical four-hit dogfood brief (`docs/evidence/dogfood-state.json`), verbatim | 4509 | 4 | none | direct comparison with the historical baseline |
| R2 | one-sentence idea: a habit tracker that asks one question a day | 67 | 10 | none | compounding budget growth from a tiny base over ten hits |
| R3 | shared grocery list with three explicit non-negotiables | 633 | 4 | 3 `--constraint` | survival of explicit owner requirements |
| R4 | weekly ops review, output requested in Finnish as a <=400-word bulleted checklist | 535 | 4 | none | whether a requested form, language and length are followed |

R2 carries the ten-hit count because the compounding budget question in #6 is about
runaway growth from a small base; the other three stay at four hits to keep the
comparison bounded.

## Historical baseline (for R1)

Four hits, same default pair, recorded in `docs/evidence/dogfood-state.json`:

- Brief 4489 chars; per-hit version sizes 7531, 15926, 19730, 20182 chars.
- Growth 4.5x the brief over four hits; `final.md` 22320 chars.

## Recorded per run

Player/model selection, hit count, input/output sizes, explicit requirement
preservation, unresolved questions, and whether the requested output form was
followed — with the engine's `final.md` kept separate from the host-written
`deliverable.md`.

## Results

All four runs completed with status `done`, no faults, and no engine errors.
Sizes are characters unless stated.

| Run | Hits | Brief | First version | Last version | Last/brief | Last/first | `final.md` | Host `deliverable.md` |
|-----|------|-------|---------------|--------------|-----------|-----------|-----------|----------------------|
| R1 | 4/4 | 4489 | 5964 | 17106 | 3.8x | 2.9x | 26570 | 18273 |
| R2 | 10/10 | 66 | 185 | 826 | 12.5x | 4.5x | 4477 | 315 words |
| R3 | 4/4 | 632 | 1028 | 1540 | 2.4x | 1.5x | 6117 | 415 words |
| R4 | 4/4 | 525 | 755 | 1069 | 2.0x | 1.4x | 3406 | 186 words |

Wall clock, from the recorded per-hit seconds: R1 637 s (longest single hit
282 s), R2 194 s, R3 173 s, R4 138 s. The slowest hits were Codex rewriting a
large document; nothing approached a runaway duration.

### R1 against the historical baseline

Same brief, same default pair, same four hits. The historical run grew
4489 -> 20182 (4.5x the brief); this run grew 4489 -> 17106 (3.8x). Per-hit
sizes went 7531/15926/19730/20182 historically against 5964/10754/13585/17106
now. The shape of the outcome is unchanged: a ticket-ready spec in vertical
slices, which is the form the brief requested. No improvement in retention is
claimed from this single pair of runs; the two are within ordinary run-to-run
variation.

One honest caveat about R1 as a quality probe: the historical brief predates
several owner decisions, so the rally faithfully re-proposed work since cut
(API transports and extra CLI players, an adapters/compat table and cached
doctor probe, a judge/scoring model, the host pet). The host deliverable flags
those slices as historical. This is the brief being stale, not the engine
drifting.

### Explicit requirement preservation (R3)

All three owner non-negotiables were seeded as `O-1`..`O-3` and all three are
standing at the end. More important than their ledger presence, the final
version honors them in its own words: "One self-contained HTML file, including
QR encoding/decoding: no build, packages, account or login. List data stays on
the two phones; no server receives it."

The mechanism also caught two attempts to design a requirement away. Players
proposed sending the list through a messaging app and through a URL fragment;
both are server round-trips, both were dropped with reasons (`P-1`, `P-2`,
`P-8`), and `final.md` surfaced them under "Owner requirements agents proposed
changing". The rally then stated the consequence plainly rather than papering
over it: "When apart, phones cannot exchange updates ... Immediate remote
updates are unavailable under these constraints" - which directly contradicts
the brief's own wish that the shopper "sees it immediately". Choosing the
constraint over the wish, and asking the owner about it in the one remaining
open question, is the behavior the ledger exists to produce.

### Requested output form (R4)

The brief asked, in Finnish, for a one-page checklist for the team lead, at most
400 words, bullets only, no essay, no tables, no code. Every layer honored it:
the rally's hits, critiques, changes and ledger entries are all in Finnish, the
last version is 147 words in 9 bullets, and the host deliverable is 186 words in
9 bullets. Each bullet says what the lead does and when. Form, language, audience
and length all followed, with no output interview and no classification step.

### Length control, as evidence for #6

The per-hit budget is relative to the incoming draft (open 1.6x, deepen 1.3x,
close 1.0x), so the allowance compounds: 11.7x over ten compliant hits, and
roughly 137x over twenty. The live runs show that the compounding ceiling is not
the real problem, and that a different effect is:

- **Players treat the budget as a target, not a cap.** R2 filled 96%, 88%, 100%,
  93%, 94%, 89%, 97% of its allowance across the open and deepen hits, including
  one hit landing exactly on the budget (419/419) and R3 landing exactly on its
  own (1336/1336). Growth stopped only when the close phase forced 1.0x - the
  phase rule, not player judgment, produced convergence.
- **The compounding allowance is never approached, because under-filling
  compounds downward too.** R2 used 4.5x its first version where 11.7x was
  allowed. The multiplier chain is applied to actual sizes, so it self-damps.
- **The rewrite attempt is weak where it matters most.** 3 of 22 hits finished
  over budget. R3's hit 1 missed by 1.7% (17 characters), which is noise. R1's
  hit 4 is the real case: Codex returned 18947 against a 13585 budget, the one
  rewrite brought it to 17106, and the engine accepted and flagged a draft still
  26% over. On large documents one rewrite buys roughly a 10% reduction.
- **`lines_kept` is not usable as a retention signal at these sizes.** It read
  0.0 on every hit of R2 and R3 and 0.0-0.18 on R1 and R4, including hits whose
  own `changes` said "tightened wording while preserving all decisions". Short
  documents get reflowed, so verbatim line retention measures formatting. It
  remains telemetry; it is not a quality score, and the handover should not be
  read as implying otherwise.

**Recommendation for #6.** Keep the phase multipliers against the incoming draft
- players demonstrably respect them, and the close-phase 1.0x is what produces
convergence. Add one non-compounding absolute ceiling anchored to the first
version, so the allowance cannot ratchet with hit count: no hit may exceed five
times the serve. Five is the smallest round multiple that admits every compliant
run observed here (R2 needed 4.5x over ten hits; R1, R3 and R4 needed 1.4-2.9x).
Do not add a new tolerance for trivial overage: a 17-character miss is already
only a flag, and the flag is cheap. Do not add a second rewrite attempt; the
evidence is that one rewrite recovers about 10% on a large document, so a second
would not close a 26% gap either, and it would double the cost of the slowest
hit in the set.

### Player decisions, as evidence for the ledger question

Owner entries earned their place: R3 is a direct demonstration that `O-*`
entries plus the conflict report stopped two requirement violations and made the
trade-off visible to the owner.

Player entries are a different story. They accumulate without consolidating:

- R1 reached 24 standing player entries in four hits, against the render cap of
  25. A slightly longer rally on that brief would have started evicting.
- R2 reached 22 standing entries for an 826-character idea - the ledger was
  larger than the artifact it governed. Six of them (`P-8`, `P-10`, `P-13`,
  `P-14`, `P-15`, `P-16`) restate one decision: the day locks at local midnight.
- No run produced a single dispute, and only R3 produced drops.

So player entries do add value beyond persistent owner instructions - R2's final
version does carry all of them - but they add it inefficiently, and a ten-hit
rally on a larger brief will hit the cap. Per #24 the mechanism stays unchanged
and no schema is added; the recommendation to record is that the next change
here should be consolidation or a lower cap for `P-*` entries only, never for
`O-*`, and that it should be decided on its own evidence rather than bundled
into #6.

### Wall-clock cap, as evidence for #8

The longest run was 10.6 minutes of model time across four hits, and the longest
single hit was 282 seconds. Cancellation and resume already leave a usable
`final.md`, which these runs did not need to exercise. Nothing here shows the
existing cancellation to be insufficient, so #8 should stay deferred on this
evidence rather than acquire a timer.

## Limitations

- Four runs, one player pair, one account, one day. These are observations, not
  measurements; no statistical claim is made about any ratio above.
- R1 is a single pair of runs against a single historical baseline, so the
  3.8x-versus-4.5x difference is not evidence of improvement either way.
- The engine chooses no model alias, so the effective models are whatever the two
  CLIs defaulted to for this account on 2026-10-13. A later default changes the
  numbers.
- Semantic preservation was judged by reading the outputs, by one reader.
- No run exercised faults, fatal errors, owner notes, resume, or cancellation;
  those stay covered by the credential-free suite only.
- R2's 12.5x brief-to-outcome ratio is an artifact of a 66-character brief, not a
  growth problem; the first-version anchor is the meaningful denominator.
