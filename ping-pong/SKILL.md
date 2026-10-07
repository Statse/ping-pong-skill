---
name: ping-pong
description: Ping-pong an idea between two configurable agent sessions for a set number of hits, then turn the refined idea into a deliverable (a one-shot build prompt, a ticket-ready spec, or whatever fits a non-code idea). Use when the user says "ping-pong", "/ping-pong", or wants an idea rallied, bounced, or cross-refined between models.
---

# Ping-pong

Two configurable agent CLI sessions rally one idea; both may use the same CLI. Each **hit** = one model receives the current version plus its opponent's notes, critiques it, and returns an improved version. Early hits open the idea up, middle hits deepen it, late hits converge. You are the umpire: you start the rally, watch it, and turn the last version into the deliverable.

Arguments: the **idea** (text or a file path) and the **iterations** (total alternating turns, default 10). `/ping-pong 14 Tinder for houses` means fourteen turns, normally seven per player. Respect requests to disable the animation.

## Steps

1. **Take the arguments.** If the idea is missing, ask for it. Write it to `idea.md` in the working directory if it is longer than a sentence or two. Done when you have the idea and a hit count.

2. **Pick and preflight the players.** Run `python3 scripts/rally.py --list-players` (paths are relative to this skill's folder). If the user named models, use their specs; otherwise accept the auto pick. The engine preflights both selected players automatically when starting. Use `python3 scripts/rally.py doctor --players a,b` only for a separate diagnostic check; it sends additional provider requests. If preflight fails, report the issue.

3. **Start the rally** in the background, so the long run does not hit a tool timeout:
   ```
   python3 scripts/rally.py --idea-file idea.md -n <hits> [--players a,b]
   ```
   Add `--animation` only when the host can embed the local widget described in [DISPLAY.md](DISPLAY.md); otherwise omit it. Respect the saved preference and `--no-animation`. Done when the process is running and `state.json` exists in its printed directory.

4. **Follow the rally.** Use `python3 scripts/rally.py wait --dir <dir> --after 0 --timeout 60`, then advance `--after` to each returned event ID until `done`, `error`, or `stopped`. Agents receive the current hit, remaining count, and a phase scaled to the total: about 30% explore, 40% deepen, 30% converge. A turn over its character budget gets one rewrite attempt. Relay owner notes with `python3 scripts/rally.py note --dir <dir> "text"`; later turns keep them. Resume interrupted runs with `python3 scripts/rally.py resume --dir <dir>`. Fatal errors such as token/context limits stop immediately; report the cause and partial result. The optional display is only two pixel paddles and a ball looping while work runs. Relay “disable animation” with `python3 scripts/rally.py animation off`; this persists and never stops the rally. See [DISPLAY.md](DISPLAY.md) for embedding. Do not modify host settings or open an external browser automatically.

5. **Check the rally.** Read `final.md` and skim each hit's `changes` and `owner_conflicts` in `state.json`. Confirm explicit owner requirements remain; a proposed change is not owner approval. Report drift if players substantially rewrote the idea. If the rally stopped, report the cause and partial result.

6. **Shape the deliverable.** Use your judgment to choose and write the most useful output from [OUTPUTS.md](OUTPUTS.md):
   - **Not code** → the form that makes the idea most usable (plan, pitch, outline, brief…).
   - **Code, one-shot** → a one-shot build prompt. It qualifies only if all hold: one deployable unit, no open decision blocks the build, acceptance can be checked in one session.
   - **Code, larger** → a ticket-ready spec, structured as vertical slices so `/to-tickets` or `/to-issues` can split it directly.
   Write it in the language of the original idea. Save it as `deliverable.md` in the rally dir. Done when every open question from the rally is either resolved in the deliverable or listed in its open-questions section.

7. **Report.** Give the user: the deliverable, the three biggest changes (who made them), the open questions, and the path to `deliverable.md`. For a ticket-ready spec, offer to run `/to-tickets` on it.

## Install

Copy the `ping-pong` folder to the host's skills directory: `~/.claude/skills/` (Claude Code; Cursor also reads it), `~/.codex/skills/`, `~/.cursor/skills/`, or `~/.config/opencode/skills/`. Needs Python 3.

## Dry run

`python3 scripts/rally.py --idea "test" -n 4 --players mock:left,mock:right` plays a fake rally in ~15 s. Use it to check the setup; add `--animation` when testing an embedded display.
