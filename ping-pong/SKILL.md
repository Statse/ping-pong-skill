---
name: ping-pong
description: Ping-pong an idea between two configurable agent sessions for a set number of hits, then return the refined idea in the form the brief asked for (a plan, a pitch, a spec, a one-shot build prompt, or a standalone refined idea by default). Use when the user says "ping-pong", "/ping-pong", or wants an idea rallied, bounced, or cross-refined between models.
---

# Ping-pong

Two configurable agent CLI sessions rally one idea; both may use the same CLI. Each **hit** = one model receives the current version plus its opponent's notes, critiques it, and returns an improved version. Early hits open the idea up, middle hits deepen it, late hits converge. You are the umpire: you start the rally, watch it, and turn the last version into one outcome — the form the brief asked for, or a standalone refined idea when it asked for none.

Arguments: the **idea** (text or a file path) and the **iterations** (total alternating turns, default 10). `/ping-pong 14 Tinder for houses` means fourteen turns, normally seven per player. Respect requests to disable the animation.

## Steps

1. **Take the arguments.** If the idea is missing, ask for it. Keep the brief whole, including any instruction about form, language, audience or length: the engine relays it to every hit. Write it to `idea.md` in the working directory if it is longer than a sentence or two. Done when you have the brief and a hit count.

2. **Pick and preflight the players.** Run `python3 scripts/rally.py --list-players` (paths are relative to this skill's folder). Supported players are `cli:claude`, `cli:codex` and `cli:cursor`; the default pair is Claude then Codex, and two sessions of one CLI are fine if asked for. If the user named models, use their specs; otherwise accept the auto pick. If a CLI is missing, report which one and the supported alternatives; never substitute another provider. The engine preflights both selected players automatically when starting. Use `python3 scripts/rally.py doctor --players a,b` only for a separate diagnostic check; it sends additional provider requests. If preflight fails, report the issue.

3. **Prepare the directory, then start the rally** in the background, so the long run does not hit a tool timeout. `setup` prints a fresh directory; never guess a generated name. Repeat `--constraint` for each explicit owner non-negotiable in the user's brief — the engine seeds them as `O-*` entries players cannot drop. Infer nothing and ask nothing extra: no explicit non-negotiables means no `--constraint`, which is fine.
   ```
   dir=$(python3 scripts/rally.py setup --idea-file idea.md [--constraint "must stay free"])
   python3 scripts/rally.py --idea-file idea.md -n <hits> --out "$dir" [--players a,b]
   ```
   The directory stays an internal detail; do not ask the user to manage files. `setup` refuses a directory that already holds a rally or constraints, so nothing is overwritten.
   Add `--animation` only when the host can embed the local widget described in [DISPLAY.md](DISPLAY.md); otherwise omit it. Respect the saved preference and `--no-animation`. Done when the process is running and `state.json` exists in its printed directory.

4. **Follow the rally.** Use `python3 scripts/rally.py wait --dir <dir> --after 0 --timeout 60`, then advance `--after` to each returned event ID until `done`, `error`, or `stopped`. Agents receive the current hit, remaining count, and a phase scaled to the total: about 30% explore, 40% deepen, 30% converge. A turn over its character budget gets one rewrite attempt. Relay owner notes with `python3 scripts/rally.py note --dir <dir> "text"`; later turns keep them. Resume interrupted runs with `python3 scripts/rally.py resume --dir <dir>`. Fatal errors such as token/context limits stop immediately; report the cause and partial result. The optional display is only two pixel paddles and a ball looping while work runs. Relay “disable animation” with `python3 scripts/rally.py animation off`; this persists and never stops the rally. See [DISPLAY.md](DISPLAY.md) for embedding. Do not modify host settings or open an external browser automatically.

5. **Check the rally.** Read `final.md` and skim each hit's `changes` and `owner_conflicts` plus the `ledger` and `disputes` in `state.json`. Standing decisions, dropped ones with reasons, and refused drops are all in `final.md`. Confirm explicit owner requirements remain; a proposed change is not owner approval. Report drift if players substantially rewrote the idea. If the rally stopped, report the cause and partial result.

6. **Write the one outcome.** Do not ask the user to pick an output format. If the brief asked for a form, language, audience or length, that request wins — write exactly that, using [OUTPUTS.md](OUTPUTS.md) if it has a matching shape. Otherwise write a standalone refined idea: the shape a reader can use directly, with no build prompt or ticket spec invented for them. Synthesize the last completed version with the owner brief, owner notes and standing ledger entries; a proposed change is never owner approval, so never drop an explicit owner requirement. Keep only questions that are genuinely still open — `final.md` separates the last hit's questions from ones it stopped asking; check those against the final version, the notes and the ledger instead of relisting them, and invent no answers. Write it in the language of the brief and save it as `deliverable.md` in the rally dir. Clarify with the user only if the brief contradicts itself in a way that blocks writing.

7. **Report.** Lead with the outcome itself, then the path to `deliverable.md`, the biggest changes (who made them), and any genuinely open questions. Keep ledger, retry and event detail in `final.md` and `state.json`; surface a failure, a partial rally or a consequential owner conflict in the report. For a ticket-ready spec, offer to run `/to-tickets` on it.

## Install

Copy the `ping-pong` folder to the host's skills directory: `~/.claude/skills/` (Claude Code; Cursor also reads it), `~/.codex/skills/`, or `~/.cursor/skills/`. Needs Python 3.

## Dry run

`python3 scripts/rally.py --idea "test" -n 4 --players mock:left,mock:right` plays a fake rally in ~15 s. Use it to check the setup; add `--animation` when testing an embedded display.
