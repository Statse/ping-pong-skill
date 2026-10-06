#!/usr/bin/env python3
"""The rally pet: a tiny ping-pong court for agent UIs.

  pet.py                      one statusline line for the active rally (empty when idle)
  pet.py --wrap "<command>"   run an existing statusline command first, then add the pet line
  pet.py --frame [rally_dir]  a few lines of plain text to paste into chat

Reads ~/.ping-pong/active.json, which rally.py writes when a rally starts.
"""
import argparse
import json
import math
import pathlib
import subprocess
import sys
import time

ACTIVE = pathlib.Path.home() / ".ping-pong" / "active.json"
LANE = 25
LINGER_S = 120  # keep showing "done" this long after the rally ends
ORANGE, RED, DIM, RESET = "\x1b[38;5;214m", "\x1b[38;5;160m", "\x1b[2m", "\x1b[0m"


def load(rally_dir=None):
    try:
        path = (pathlib.Path(rally_dir) / "state.json" if rally_dir
                else pathlib.Path(json.loads(ACTIVE.read_text())["state"]))
        return json.loads(path.read_text())
    except (OSError, ValueError, KeyError):
        return None


def ball_x(s):
    """Ball position 0..1 (0 = left paddle). It drifts toward whoever is thinking."""
    cur, hits = s.get("current"), s.get("hits", [])
    if not cur:
        return 0.0 if hits and hits[-1]["side"] == 0 else 1.0 if hits else 0.5
    start = 0.5 if not hits else (0.0 if hits[-1]["side"] == 0 else 1.0)
    target = 0.0 if cur["side"] == 0 else 1.0
    secs = [h["seconds"] for h in hits if h.get("seconds")]
    expected = sum(secs) / len(secs) if secs else 30
    elapsed = max(0, time.time() - cur["started_at"] / 1000)
    p = 0.93 * (1 - math.exp(-elapsed / expected))
    return start + (target - start) * p


def lane(x, color):
    pos = round(x * (LANE - 1))
    cells = []
    for i in range(LANE):
        if i == pos:
            cells.append(f"{ORANGE}●{RESET}" if color else "o")
        elif i == LANE // 2:
            cells.append("┆" if color else "|")
        else:
            cells.append(f"{DIM}·{RESET}" if color else ".")
    return "".join(cells)


def short(label, n=12):
    return label if len(label) <= n else label[: n - 1] + "…"


def line(s, color=True):
    if not s:
        return ""
    if s["status"] != "running":
        ended = (s.get("finished_at") or 0) / 1000
        if s["status"] == "done" and time.time() - ended > LINGER_S:
            return ""
        if s["status"] == "error":
            return "🏓 Rally stopped: two faults in a row."
        return f"🏓 Rally done: {len(s['hits'])} hits. Refined idea is ready."
    a, b = (short(p["label"]) for p in s["players"])
    pa = f"{RED}▌{RESET}" if color else "|"
    pb = "▐" if color else "|"
    cur = s.get("current")
    who = f"{short(s['players'][cur['side']]['label'])} thinking" if cur else "between hits"
    done = len(s["hits"])
    return f"🏓 {a} {pa}{lane(ball_x(s), color)}{pb} {b}   hit {min(done + 1, s['iterations'])}/{s['iterations']}, {who}"


def frame(s):
    if not s:
        return "No rally found."
    hits = s["hits"]
    score = [sum(1 for h in hits if h["side"] == i) for i in (0, 1)]
    a, b = (p["label"] for p in s["players"])
    out = [f"{a} {score[0]}  vs  {b} {score[1]}   ({len(hits)} of {s['iterations']} hits)",
           f"|{lane(ball_x(s), False)}|"]
    cur = s.get("current")
    if s["status"] == "running" and cur:
        secs = int(time.time() - cur["started_at"] / 1000)
        out.append(f"{s['players'][cur['side']]['label']} is working on hit {cur['n']} ({secs} s)")
    elif s["status"] == "done":
        out.append("Rally finished.")
    elif s["status"] == "error":
        out.append("Rally stopped after two faults in a row.")
    if hits:
        last = hits[-1]
        out.append(f"Last hit ({last['player']}): " + ("; ".join(last["changes"][:3]) or "no change list"))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wrap", help="existing statusline command to run first (gets the same stdin)")
    ap.add_argument("--frame", nargs="?", const="", help="print a chat frame for a rally dir (default: active)")
    ap.add_argument("--plain", action="store_true", help="no ANSI colours")
    a = ap.parse_args()

    if a.frame is not None:
        print(frame(load(a.frame or None)))
        return
    if a.wrap:
        stdin = "" if sys.stdin.isatty() else sys.stdin.read()
        try:
            r = subprocess.run(a.wrap, shell=True, input=stdin, capture_output=True, text=True, timeout=5)
            if r.stdout.strip():
                print(r.stdout.rstrip("\n"))
        except subprocess.TimeoutExpired:
            pass
    text = line(load(), color=not a.plain)
    if text:
        print(text)


if __name__ == "__main__":
    main()
