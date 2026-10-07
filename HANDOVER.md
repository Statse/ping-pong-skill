# Handover: confirmed baseline and optional animation

Updated 2026-10-06. User decisions in this conversation supersede the original display plan.

## Baseline

`/ping-pong 10 <idea>` means ten total alternating turns between two configurable agent CLI
sessions, normally five each. The host produces a plan, build prompt, or spec from the last version.
The owner explicitly confirmed this baseline. Do not redesign the refinement flow.

## Current display decision

Two small pixel paddles hit one ball back and forth while work runs. Decorative loop only; no scores,
turn visualization, dashboard, replay, or automatic external browser. It stops on completion, error,
cancellation, or disconnection. Users must be able to disable it; persistent and per-run controls exist.
Host-neutral first. The owner also requested investigation across Copilot, Claude, Codex, Cursor and CLIs.

Task: https://github.com/Statse/ping-pong-skill/issues/16
Research: `docs/host-animation-support.md` (primary sources, dated; adapters not certified).

## Working tree

Changes are local, uncommitted and unpushed. Do not commit or push without being asked.

- Removed old court, pet, statusline installer and OpenCode hook scripts.
- Removed old visual instructions from the skill, display guide and current spec.
- New `assets/widget.js` is an embeddable web component; `widget.html` and `adapter.js` connect it to
  the optional stdlib local server in `scripts/animation.py`.
- `--animation` exposes the widget on a free loopback port for embedding; nothing opens automatically.
- `animation off|on|status` controls `~/.ping-pong/settings.json`; `--no-animation` disables one run.
- `wait` drains ordered events; `status` is plain text. No ASCII court or visual scoreboard remains.
- Cancellation records `stopped`; CLI subprocess cleanup covers timeout and interruption.
- CI workflow tests Python 3.9/3.12 on Linux/macOS/Windows, including an empty-PATH `doctor` step and
  a credential-free mock rally. Issue #2 tracks making that six-cell matrix green on a PR.
- `.gitignore` keeps rally run directories (`.ping-pong/`) and bytecode out of the repository.

### Drift telemetry (#4)

Each hit now stores `lines_kept` and `size_ratio` in `state.json`; the serve reports both as `null`
rather than dividing by zero. `drift()` and `drift_text()` in `rally.py` are pure and unit-tested with
known-retention fixtures. The numbers surface in plain language ("rewrote 99 % of lines, 1.68x the
length") in the per-hit progress log and in `status`/`wait`.

Deviation from #4's wording: it asks for rendering in `rally.py frame` and on the court. #16 removed
both, so the plain-text `status`/`wait` output and the progress log are the surviving surfaces and
carry the numbers instead. Final-artifact reporting stays with #14.

Host-native adapters (MCP Apps, Claude mods, Codex native pet) are researched but not implemented.
The localhost widget is a working integration seam, not a claim of native embedding everywhere.

## Remaining engine work

#1 tracks the earlier v2 engine plan, detailed in `SPEC-v2.md`. #16 replaces its old display
requirements. #4 (drift telemetry) is implemented locally. Ledger, length budgets, adapters/doctor
probes, inbox, resume and structured deliverable metadata remain planned. The drift numbers exist to
verify the ledger and length-budget slices against the v1 baseline in `docs/evidence/`; the dogfood
re-run that #4's parent acceptance asks for needs paid live players and has not been done. The current doctor only checks binary availability.
Earlier API and extra CLI transports remain until their dedicated player cleanup; they were not
removed as part of animation work.

Retain `docs/evidence/`: historical live rally measurements, not current display instructions.
No protocol change was made to prompts/replies in the animation replacement, so no paid live
rally is needed for this task. Keep Python 3.9 compatibility and the stdlib-only engine.

## Validation

Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`.
Credential-free baseline: `python3 ping-pong/scripts/rally.py --idea "test" -n 4 --players mock:left,mock:right --no-animation`.
Browser verification uses an isolated temporary preference file, never the owner's saved setting.
