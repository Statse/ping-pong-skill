---
name: ping-pong
description: Ping-pong an idea between two different LLMs for a set number of hits, then turn the refined idea into a deliverable (a one-shot build prompt, a ticket-ready spec, or whatever fits a non-code idea). Use when the user says "ping-pong", "/ping-pong", or wants an idea rallied, bounced, or cross-refined between models.
---

# Ping-pong

Two models rally one idea. Each **hit** = one model receives the current version plus its opponent's notes, critiques it, and returns an improved version. Early hits open the idea up, middle hits deepen it, late hits converge. You are the umpire: you start the rally, watch it, and turn the last version into the deliverable.

Arguments: the **idea** (text or a file path) and the **iterations** (number of hits, default 6; an even number gives both players the same number of hits).

## Steps

1. **Take the arguments.** If the idea is missing, ask for it. Write it to `idea.md` in the working directory if it is longer than a sentence or two. Done when you have the idea and a hit count.

2. **Pick the players.** Run `python3 scripts/rally.py --list-players` (paths are relative to this skill's folder). If the user named models, use their specs; otherwise accept the auto pick. Done when you have exactly two player specs. If fewer than two are available, show the user [PLAYERS.md](PLAYERS.md) setup and stop.

3. **Start the rally** in the background, so the long run does not hit a tool timeout:
   ```
   python3 scripts/rally.py --idea-file idea.md -n <hits> [--players a,b]
   ```
   It opens the live court in the browser. Tell the user the court URL it prints. Done when the process is running and `state.json` exists in the rally dir it printed.

4. **Show the rally** following [DISPLAY.md](DISPLAY.md). First time per host: check `python3 scripts/setup_pet.py --host <the host you are running in> --status`; if the host supports a pet and it is not installed, offer it once, install only on a yes (for Cursor, give the user the command to run from a plain terminal instead), and tell the user it shows from their next restart. Then, about once a minute until `status` in `state.json` is `done` or `error`, paste the output of `python3 scripts/pet.py --frame` in a code block. Done when the status is final and the rally process has exited.

5. **Check the rally.** Read `final.md` and skim every hit's `changes` in `state.json`. If status is `error`, report the faults and offer to restart with other players; continue with the best version so far only if the user agrees. Done when you can name the three biggest changes from the original idea to the final version.

6. **Shape the deliverable.** Classify the refined idea and write the matching output from [OUTPUTS.md](OUTPUTS.md):
   - **Not code** → the form that makes the idea most usable (plan, pitch, outline, brief…).
   - **Code, one-shot** → a one-shot build prompt. It qualifies only if all hold: one deployable unit, no open decision blocks the build, acceptance can be checked in one session.
   - **Code, larger** → a ticket-ready spec, structured as vertical slices so `/to-tickets` or `/to-issues` can split it directly.
   Write it in the language of the original idea. Save it as `deliverable.md` in the rally dir. Done when every open question from the rally is either resolved in the deliverable or listed in its open-questions section.

7. **Report.** Give the user: the deliverable, the three biggest changes (who made them), the open questions, and the paths to `deliverable.md` and `replay.html` (replay works offline). For a ticket-ready spec, offer to run `/to-tickets` on it.

## Install

Copy the `ping-pong` folder to the host's skills directory: `~/.claude/skills/` (Claude Code; Cursor also reads it), `~/.codex/skills/`, `~/.cursor/skills/`, or `~/.config/opencode/skills/`. Needs Python 3.

## Dry run

`python3 scripts/rally.py --idea "test" -n 4 --players mock:left,mock:right` plays a fake rally in ~15 s. Use it to show the court or check the setup.
