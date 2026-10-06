#!/usr/bin/env python3
"""Ping-pong rally: bounce an idea between two LLMs for N hits.

Standard library only. Writes state.json after every hit, serves a live
court view (court.html) on localhost, and leaves final.md + replay.html.

Examples:
  rally.py --idea "A habit tracker for bands" --iterations 6
  rally.py --idea-file idea.md -n 8 --players cli:claude,cli:codex
  rally.py --idea "test" -n 4 --players mock:left,mock:right     # dry run
  rally.py --list-players
"""
import argparse
import datetime
import functools
import http.server
import json
import os
import pathlib
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser

HERE = pathlib.Path(__file__).resolve().parent
API_KINDS = ("anthropic", "openai", "gemini", "openrouter")
DEFAULT_MODELS = {
    "anthropic": os.environ.get("PINGPONG_ANTHROPIC_MODEL", "claude-sonnet-5-5"),
    "openai": os.environ.get("PINGPONG_OPENAI_MODEL", "gpt-5"),
    "gemini": os.environ.get("PINGPONG_GEMINI_MODEL", "gemini-2.5-pro"),
    "openrouter": os.environ.get("PINGPONG_OPENROUTER_MODEL", "openai/gpt-5"),
}
KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
CLI_LABELS = {"claude": "Claude Code", "codex": "Codex", "gemini": "Gemini CLI",
              "cursor": "Cursor", "opencode": "OpenCode", "copilot": "Copilot"}
CLI_VENDOR = {"claude": "anthropic", "codex": "openai", "gemini": "gemini",
              "cursor": "cursor", "opencode": "opencode", "copilot": "github"}
ACTIVE = pathlib.Path.home() / ".ping-pong" / "active.json"
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def cli_bin(tool):
    """Executable for a cli player, or None if missing."""
    if tool == "cursor":
        return shutil.which("cursor-agent") or shutil.which("agent")
    return shutil.which(tool)


# ---------------------------------------------------------------- players


class Player:
    def __init__(self, spec):
        parts = spec.strip().split(":", 2)
        self.spec = spec.strip()
        self.kind = parts[0]
        if self.kind == "cli":
            if len(parts) < 2 or not parts[1]:
                raise ValueError(f"cli player needs a tool name: {spec}")
            self.tool = parts[1]
            self.model = parts[2] if len(parts) > 2 else None
            base = CLI_LABELS.get(self.tool, self.tool)
        elif self.kind in API_KINDS:
            self.tool = None
            self.model = ":".join(parts[1:]) or DEFAULT_MODELS[self.kind]
            base = self.model
        elif self.kind == "mock":
            self.tool, self.model = None, None
            base = f"Mock {parts[1] if len(parts) > 1 else ''}".strip()
        else:
            raise ValueError(f"unknown player kind '{self.kind}' in {spec}")
        self.label = f"{base} ({self.model})" if self.kind == "cli" and self.model else base

    def to_dict(self):
        return {"spec": self.spec, "label": self.label}

    def call(self, system, user):
        if self.kind == "mock":
            return _mock(system, user)
        if self.kind == "cli":
            return _cli(self.tool, self.model, system, user)
        return _api(self.kind, self.model, system, user)


def detect_players():
    found = []
    for tool in ("claude", "codex", "cursor", "opencode", "copilot", "gemini"):
        if cli_bin(tool):
            found.append(f"cli:{tool}")
    for kind in API_KINDS:
        if os.environ.get(KEY_ENV[kind]):
            found.append(f"{kind}:{DEFAULT_MODELS[kind]}")
    return found


def auto_pick(found):
    """Two players, preferring different vendors."""
    def vendor(spec):
        kind, _, rest = spec.partition(":")
        return CLI_VENDOR.get(rest.split(":")[0], rest) if kind == "cli" else kind
    picked = []
    for s in found:
        if not picked or vendor(s) != vendor(picked[0]):
            picked.append(s)
        if len(picked) == 2:
            return picked
    if len(picked) == 1:  # one vendor only: split it into two different models
        only = picked[0]
        if only == "cli:claude":
            return ["cli:claude:opus", "cli:claude:sonnet"]
        if only.startswith("anthropic:"):
            return ["anthropic:claude-opus-5-5", "anthropic:claude-sonnet-5-5"]
    return picked


# ---------------------------------------------------------------- transports


def _post(url, body, headers, timeout=900):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} from {url.split('?')[0]}: "
                           f"{e.read().decode(errors='replace')[:400]}") from None


def _api(kind, model, system, user):
    key = os.environ.get(KEY_ENV[kind])
    if not key:
        raise RuntimeError(f"{KEY_ENV[kind]} is not set")
    if kind == "anthropic":
        r = _post("https://api.anthropic.com/v1/messages",
                  {"model": model, "max_tokens": 8000, "system": system,
                   "messages": [{"role": "user", "content": user}]},
                  {"x-api-key": key, "anthropic-version": "2023-06-01"})
        return "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text")
    if kind in ("openai", "openrouter"):
        base = "https://api.openai.com/v1" if kind == "openai" else "https://openrouter.ai/api/v1"
        r = _post(f"{base}/chat/completions",
                  {"model": model, "messages": [{"role": "system", "content": system},
                                                {"role": "user", "content": user}]},
                  {"Authorization": f"Bearer {key}"})
        return r["choices"][0]["message"]["content"]
    if kind == "gemini":
        r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                  {"systemInstruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": user}]}]}, {})
        return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
    raise RuntimeError(f"no transport for {kind}")


def _cli(tool, model, system, user):
    prompt = f"{system}\n\n---\n\n{user}"
    workdir = tempfile.mkdtemp(prefix="pingpong-")  # keep agent CLIs away from the user's repo
    out_file = os.path.join(workdir, "last.txt")
    stdin = None
    exe = cli_bin(tool)
    if not exe:
        raise RuntimeError(f"'{tool}' is not on PATH")
    m = lambda flag: [flag, model] if model else []
    if tool == "claude":
        cmd = [exe] + m("--model") + ["-p", prompt]
    elif tool == "codex":
        cmd = [exe, "exec", "--skip-git-repo-check", "--output-last-message", out_file] + m("-m") + [prompt]
    elif tool == "cursor":
        cmd = [exe, "-p", "--trust", "--mode", "ask", "--output-format", "text"] + m("--model") + [prompt]
    elif tool == "opencode":
        cmd = [exe, "run"] + m("-m") + [prompt]
    elif tool == "copilot":
        cmd = [exe, "-s"] + m("--model") + ["-p", prompt]
    elif tool == "gemini":
        cmd = [exe] + m("-m") + ["-p", prompt]
    else:  # any other command: prompt on stdin, answer on stdout
        cmd, stdin = [exe], prompt
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=workdir, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"{tool} exited {p.returncode}: {(p.stderr or p.stdout)[-400:]}")
    if tool == "codex" and os.path.exists(out_file):
        return pathlib.Path(out_file).read_text()
    return ANSI.sub("", p.stdout)


def _mock(system, user):
    time.sleep(random.uniform(2.5, 5))
    n = re.search(r"hit (\d+) of", system)
    return json.dumps({
        "critique": "Mock critique: the core is sound, the audience is fuzzy.",
        "version": f"# Mock version after hit {n.group(1) if n else '?'}\n\n" + user[-300:],
        "changes": ["Sharpened the audience", "Cut one feature"],
        "open_questions": ["Who pays for this?"],
    })


# ---------------------------------------------------------------- prompts

SYSTEM = """You are {me}, playing an idea ping-pong rally against {them}. You take turns improving one idea. This is hit {n} of {total}.

Phase of this hit: {phase}

How to return the ball:
- Read the current version and your opponent's notes.
- Keep what is strong. Name what is weak, vague, risky or missing, and fix it in your version.
- Refine the current version rather than restarting it; keep concrete details unless you have a reason to drop them.
- Your version must stand alone: someone who reads only it gets the whole idea.
- Write in the language of the owner's original idea.

Reply with only this JSON object:
{{"critique": "honest, specific notes on the incoming version",
 "version": "the full improved idea, markdown allowed",
 "changes": ["one short line per change you made"],
 "open_questions": ["questions only the idea's owner can answer"]}}"""

PHASES = {
    "open": "Open up. Challenge assumptions, find the stronger angle, add what is missing.",
    "deepen": "Deepen. Make it concrete: specifics, structure, edge cases, trade-offs.",
    "close": "Close out. Converge: tighten, cut what does not earn its place, resolve contradictions. No new big features.",
}


def phase_for(n, total):
    if n == total:
        return "close"
    frac = (n - 1) / max(total - 1, 1)
    return "open" if frac < 0.34 else "deepen" if frac < 0.67 else "close"


def user_prompt(idea, prev, them):
    head = f"Original idea from the owner:\n\n{idea}\n"
    if prev is None:
        return head + "\nYou serve: there is no previous version yet. Write the first version."
    changes = "\n".join(f"- {c}" for c in prev["changes"]) or "- (none listed)"
    return (f"{head}\n---\nCurrent version (from {them}, hit {prev['n']}):\n\n{prev['version']}\n"
            f"\n---\n{them}'s notes on the version before:\n{prev['critique'] or '(none)'}\n"
            f"\nChanges {them} made:\n{changes}\n")


def parse_reply(text):
    candidates = [text]
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        candidates.append(fence.group(1))
    if "{" in text:
        candidates.append(text[text.index("{"): text.rindex("}") + 1])
    for c in candidates:
        try:
            d = json.loads(c)
            if isinstance(d, dict) and d.get("version"):
                return {"critique": str(d.get("critique", "")),
                        "version": str(d["version"]),
                        "changes": [str(x) for x in d.get("changes") or []],
                        "open_questions": [str(x) for x in d.get("open_questions") or []],
                        "parsed": True}
        except (ValueError, TypeError):
            continue
    return {"critique": "", "version": text.strip(), "changes": [], "open_questions": [], "parsed": False}


# ---------------------------------------------------------------- state + court


class Rally:
    def __init__(self, idea, total, players, out):
        self.out = out
        self.state = {
            "idea": idea, "iterations": total, "players": [p.to_dict() for p in players],
            "hits": [], "faults": [], "current": None, "status": "running",
            "started_at": _now_ms(), "finished_at": None,
        }
        self.save()

        ACTIVE.parent.mkdir(exist_ok=True)
        ACTIVE.write_text(json.dumps({"state": str(self.out / "state.json")}))

    def save(self):
        tmp = self.out / "state.json.tmp"
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1))
        os.replace(tmp, self.out / "state.json")


def _now_ms():
    return int(time.time() * 1000)


def serve(out, port):
    handler = functools.partial(_QuietHandler, directory=str(out))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class Ticker:
    """Terminal ball flying between paddles while a player thinks."""
    W = 34

    def __init__(self, players):
        self.players, self.stop_evt, self.thread = players, threading.Event(), None
        self.tty = sys.stdout.isatty()

    def fly(self, n, total, side, expected_s):
        a, b = self.players[0].label[:14], self.players[1].label[:14]
        hitter = self.players[side].label
        if not self.tty:
            print(f"hit {n}/{total}: ball flying to {hitter} ...", flush=True)
            return
        self.stop_evt.clear()

        def run():
            t0 = time.time()
            while not self.stop_evt.is_set():
                p = min(0.95, 1 - 2.71828 ** (-(time.time() - t0) / expected_s))
                x = int((p if side == 1 else 1 - p) * (self.W - 1))
                lane = "".join("o" if i == x else ("|" if i == self.W // 2 else "·") for i in range(self.W))
                sys.stdout.write(f"\r{a:>14} ▌{lane}▐ {b:<14}  hit {n}/{total}  {int(time.time()-t0)}s ")
                sys.stdout.flush()
                time.sleep(0.12)
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def land(self, msg):
        if self.thread:
            self.stop_evt.set()
            self.thread.join()
            self.thread = None
            sys.stdout.write("\r" + " " * 100 + "\r")
        print(msg, flush=True)


# ---------------------------------------------------------------- main loop


def play(idea, total, players, out, ticker):
    rally = Rally(idea, total, players, out)
    prev, side, durations, consecutive_faults = None, 0, [], 0
    n = 1
    while n <= total:
        me, them = players[side], players[1 - side]
        rally.state["current"] = {"n": n, "side": side, "started_at": _now_ms()}
        rally.save()
        expected = sum(durations) / len(durations) if durations else 30
        ticker.fly(n, total, side, expected)
        system = SYSTEM.format(me=me.label, them=them.label, n=n, total=total,
                               phase=PHASES[phase_for(n, total)])
        t0 = time.time()
        reply, err = None, None
        for _ in range(2):
            try:
                reply = parse_reply(me.call(system, user_prompt(idea, prev, them.label)))
                break
            except Exception as e:  # noqa: BLE001 - surface any transport failure as a fault
                err = str(e)
        took = time.time() - t0
        if reply is None:
            consecutive_faults += 1
            rally.state["faults"].append({"n": n, "side": side, "player": me.label, "error": err})
            rally.save()
            ticker.land(f"  fault: {me.label} could not return hit {n}: {err}")
            if consecutive_faults >= 2:
                rally.state["status"] = "error"
                rally.state["current"] = None
                rally.save()
                return rally
            side = 1 - side  # opponent takes the hit
            continue
        consecutive_faults = 0
        durations.append(took)
        hit = {"n": n, "side": side, "player": me.label, "seconds": round(took, 1), **reply}
        rally.state["hits"].append(hit)
        rally.save()
        ticker.land(f"  hit {n}/{total} by {me.label} in {took:.0f}s"
                    + (f": {hit['changes'][0]}" if hit["changes"] else ""))
        prev, side, n = hit, 1 - side, n + 1
    rally.state["status"] = "done"
    rally.state["current"] = None
    rally.state["finished_at"] = _now_ms()
    rally.save()
    return rally


def write_outputs(rally):
    s, out = rally.state, rally.out
    if s["hits"]:
        last = s["hits"][-1]
        questions = []
        for h in s["hits"]:
            for q in h["open_questions"]:
                if q not in questions:
                    questions.append(q)
        lines = [last["version"].rstrip(), "", "---", "",
                 f"Rally: {len(s['hits'])} hits between "
                 + " and ".join(p["label"] for p in s["players"]) + "."]
        if questions:
            lines += ["", "Open questions raised during the rally:"] + [f"- {q}" for q in questions]
        (out / "final.md").write_text("\n".join(lines) + "\n")
    court = (HERE / "court.html").read_text()
    payload = json.dumps(s, ensure_ascii=False).replace("</", "<\\/")
    (out / "replay.html").write_text(court.replace("/*RALLY*/null", payload, 1))


def main():
    ap = argparse.ArgumentParser(description="Bounce an idea between two LLMs.")
    ap.add_argument("--idea", help="the idea as text")
    ap.add_argument("--idea-file", help="read the idea from a file")
    ap.add_argument("-n", "--iterations", type=int, default=6, help="number of hits (default 6)")
    ap.add_argument("--players", help="two comma-separated specs, e.g. cli:claude,cli:codex")
    ap.add_argument("--out", help="rally directory (default ./.ping-pong/<timestamp>-<slug>)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-court", action="store_true", help="skip the live browser view")
    ap.add_argument("--no-browser", action="store_true", help="serve the court but do not open it")
    ap.add_argument("--linger", type=int, default=4, help="seconds to keep serving after the rally")
    ap.add_argument("--list-players", action="store_true")
    a = ap.parse_args()

    if a.list_players:
        found = detect_players()
        print("detected:", ", ".join(found) or "nothing")
        print("auto pick:", ", ".join(auto_pick(found)) or "none")
        return 0

    idea = pathlib.Path(a.idea_file).read_text() if a.idea_file else a.idea
    if not idea or not idea.strip():
        ap.error("give --idea or --idea-file")
    if a.iterations < 1:
        ap.error("--iterations must be at least 1")
    specs = [s for s in (a.players.split(",") if a.players else auto_pick(detect_players())) if s.strip()]
    if len(specs) != 2:
        print("Need exactly two players; found: " + (", ".join(specs) or "none")
              + ". See PLAYERS.md for setup.", file=sys.stderr)
        return 2
    players = [Player(s) for s in specs]

    slug = re.sub(r"[^a-z0-9]+", "-", idea.lower())[:32].strip("-") or "idea"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = pathlib.Path(a.out or f".ping-pong/{stamp}-{slug}").resolve()
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "court.html", out / "index.html")

    srv = None
    if not a.no_court:
        try:
            srv = serve(out, a.port)
            url = f"http://127.0.0.1:{a.port}/"
            print(f"court: {url}", flush=True)
            if not a.no_browser:
                webbrowser.open(url)
        except OSError as e:
            print(f"court unavailable ({e}); continuing without it", flush=True)

    print(f"rally: {players[0].label} vs {players[1].label}, {a.iterations} hits", flush=True)
    rally = play(idea.strip(), a.iterations, players, out, Ticker(players))
    write_outputs(rally)
    print(f"status: {rally.state['status']}")
    print(f"dir: {out}")
    if (out / "final.md").exists():
        print(f"final: {out / 'final.md'}")
    print(f"replay: {out / 'replay.html'}")
    if srv:
        time.sleep(a.linger)
        srv.shutdown()
    return 0 if rally.state["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
