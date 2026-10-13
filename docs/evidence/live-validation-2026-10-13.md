# Live outcome-quality validation (#24) — 2026-10-13

Pre-registered before any provider request was sent. Results are appended below
after the runs; nothing in the selection was chosen after seeing an outcome.

## Environment

- Engine: this branch (`publish()` retry for #31 included). Python 3.9.6, stdlib only.
- Players: `cli:claude` (Claude Code 2.1.291) serving, `cli:codex` (codex-cli 0.160.0)
  returning. This is the engine's default pair; no model alias is chosen by the engine,
  so the effective model is each CLI's own default for this account.
- Rally directories under `/tmp/pp-live/.ping-pong/`, outside the repo.

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

Pending: appended after the runs complete.
