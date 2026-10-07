#!/usr/bin/env python3
"""Ping-pong rally: bounce an idea between two LLMs for N hits.

Standard library only. Writes state.json after every hit, serves a live
optional pixel animation for embedding, and leaves final.md.

Examples:
  rally.py --idea "A habit tracker for bands" --iterations 10
  rally.py --idea-file idea.md -n 8 --players cli:claude,cli:codex
  rally.py --idea "test" -n 4 --players mock:left,mock:right     # dry run
  rally.py --list-players
"""
import argparse
from contextlib import contextmanager
import datetime
import json
import math
import os
import pathlib
import random
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

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
        if r.get("stop_reason") == "max_tokens":
            raise RuntimeError("token limit reached (Anthropic stop_reason=max_tokens)")
        return "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text")
    if kind in ("openai", "openrouter"):
        base = "https://api.openai.com/v1" if kind == "openai" else "https://openrouter.ai/api/v1"
        r = _post(f"{base}/chat/completions",
                  {"model": model, "messages": [{"role": "system", "content": system},
                                                {"role": "user", "content": user}]},
                  {"Authorization": f"Bearer {key}"})
        if r.get("choices") and r["choices"][0].get("finish_reason") == "length":
            raise RuntimeError("token limit reached (provider finish_reason=length)")
        return r["choices"][0]["message"]["content"]
    if kind == "gemini":
        r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                  {"systemInstruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": user}]}]}, {})
        if r.get("candidates") and r["candidates"][0].get("finishReason") == "MAX_TOKENS":
            raise RuntimeError("token limit reached (Gemini finishReason=MAX_TOKENS)")
        return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
    raise RuntimeError(f"no transport for {kind}")


def _cli(tool, model, system, user):
    prompt = f"{system}\n\n---\n\n{user}"
    exe = cli_bin(tool)
    if not exe:
        raise RuntimeError(f"'{tool}' is not on PATH")
    workdir = tempfile.mkdtemp(prefix="pingpong-")  # keep agent CLIs away from the user's repo
    out_file = os.path.join(workdir, "last.txt")
    stdin = None
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
    try:
        p = run_cli(cmd, stdin, workdir, timeout=1800)
        if p.returncode != 0:
            raise RuntimeError(
                f"{tool} exited {p.returncode} ({format_command(cmd)}): "
                f"{(p.stderr or p.stdout)[-400:]}")
        if tool == "codex" and os.path.exists(out_file):
            return pathlib.Path(out_file).read_text(encoding="utf-8")
        return ANSI.sub("", p.stdout)
    finally:
        shutil.rmtree(workdir)


def format_command(cmd):
    """Render an argv list for logs/errors. Windows uses list2cmdline, not shlex."""
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return " ".join(shlex.quote(part) for part in cmd)


def run_cli(cmd, stdin, workdir, timeout):
    """On timeout, clean up the CLI's children as well as its main process."""
    options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
               else {"start_new_session": True})
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, encoding="utf-8",
                          cwd=workdir, **options) as child:
        try:
            stdout, stderr = child.communicate(stdin, timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if child.poll() is None:
                child.kill()
            child.communicate()
            raise
        return subprocess.CompletedProcess(cmd, child.returncode, stdout, stderr)


def _mock(system, user):
    if "preflight player" in system:
        return '{"critique":"ok","version":"pong","changes":[],"open_questions":[]}'
    time.sleep(random.uniform(2.5, 5))
    n = re.search(r"hit (\d+) of", system)
    limit = re.search(r"Maximum version length for this hit: (\d+)", system)
    budget = int(limit.group(1)) if limit else 1000
    prefix = f"# Mock version after hit {n.group(1) if n else '?'}\n\n"
    body = user[-max(0, budget - len(prefix)):]
    return json.dumps({
        "critique": "Mock critique: the core is sound, the audience is fuzzy.",
        "version": (prefix + body)[:budget],
        "changes": ["Sharpened the audience", "Cut one feature"],
        "open_questions": ["Who pays for this?"],
    })


# ---------------------------------------------------------------- prompts

SYSTEM = """You are {me}, playing an idea ping-pong rally against {them}. You take turns improving one idea. This is hit {n} of {total}; {remaining} iterations remain after this one.

Phase of this hit: {phase}
Maximum version length for this hit: {budget} characters. Return a concise version within this limit.

How to return the ball:
- Read the current version and your opponent's notes.
- Keep what is strong. Name what is weak, vague, risky or missing, and fix it in your version.
- Refine the current version rather than restarting it; keep concrete details unless you have a reason to drop them.
- Never silently remove or contradict an explicit owner requirement. If you think one should change, preserve it and report the conflict with a reason for the owner.
- Your version must stand alone: someone who reads only it gets the whole idea.
- Write in the language of the owner's original idea.

Reply with only this JSON object:
{{"critique": "honest, specific notes on the incoming version",
 "version": "the full improved idea, markdown allowed",
 "changes": ["one short line per change you made"],
 "open_questions": ["questions only the idea's owner can answer"],
 "owner_conflicts": [{{"item": "owner requirement", "reason": "why it should change"}}]}}"""

PHASES = {
    "open": "Open up. Challenge assumptions, find the stronger angle, add what is missing.",
    "deepen": "Deepen. Make it concrete: specifics, structure, edge cases, trade-offs.",
    "close": "Close out. Converge: tighten, cut what does not earn its place, resolve contradictions. No new big features.",
}


def phase_for(n, total):
    """Scale explore, deepen, and converge phases to the requested count."""
    if total == 1:
        return "close"
    if total == 2:
        return "open" if n == 1 else "close"
    open_end = max(1, int(total * 0.30))
    close_start = max(open_end + 1, total - int(total * 0.30) + 1)
    if n <= open_end:
        return "open"
    if n >= close_start:
        return "close"
    return "deepen"


def remaining_iterations(n, total):
    return max(0, total - n)


def size_budget(phase, incoming_size):
    """Maximum version size for a phase, measured against the incoming draft."""
    multiplier = {"open": 1.6, "deepen": 1.3, "close": 1.0}[phase]
    return max(1, int(incoming_size * multiplier))


def user_prompt(idea, prev, them, owner_notes=None):
    head = f"Original idea from the owner:\n\n{idea}\n"
    if owner_notes:
        head += "\nOwner notes (these are authoritative and persist for the rest of the rally):\n"
        head += "\n".join(f"- {note}" for note in owner_notes) + "\n"
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
    if "{" in text and "}" in text:
        candidates.append(text[text.index("{"): text.rindex("}") + 1])
    for c in candidates:
        try:
            d = json.loads(c)
            if isinstance(d, dict) and d.get("version"):
                return {"critique": str(d.get("critique", "")),
                        "version": str(d["version"]),
                        "changes": [str(x) for x in d.get("changes") or []],
                        "open_questions": [str(x) for x in d.get("open_questions") or []],
                        "owner_conflicts": [x for x in d.get("owner_conflicts") or [] if isinstance(x, dict)],
                        "parsed": True}
        except (ValueError, TypeError):
            continue
    return {"critique": "", "version": text.strip(), "changes": [], "open_questions": [], "parsed": False}


# ---------------------------------------------------------------- drift


def drift(previous, version):
    """How much of the incoming version survived into the outgoing one.

    lines_kept is the share of the incoming version's substantial lines kept
    verbatim; size_ratio is the outgoing length over the incoming length. Both
    are None on the serve, where there is no incoming version to compare with.
    """
    incoming = (previous or "").strip()
    outgoing = (version or "").strip()
    if not incoming:
        return {"lines_kept": None, "size_ratio": None}
    kept = {line.strip() for line in outgoing.splitlines()}
    substantial = [line for line in (l.strip() for l in incoming.splitlines()) if len(line) > 20]
    return {
        "lines_kept": (round(sum(1 for line in substantial if line in kept) / len(substantial), 3)
                       if substantial else None),
        "size_ratio": round(len(outgoing) / len(incoming), 2),
    }


def drift_text(hit):
    """One hit's drift in plain language, or '' for a hit with nothing to compare."""
    kept, ratio = hit.get("lines_kept"), hit.get("size_ratio")
    if ratio is None:
        return ""
    parts = []
    if kept is not None:
        parts.append(f"rewrote {round((1 - kept) * 100)} % of lines")
    parts.append(f"{ratio:.2f}x the length")
    return ", ".join(parts)


# ---------------------------------------------------------------- state + events


class Rally:
    def __init__(self, idea, total, players, out, start=True):
        self.out = out
        self.started = False
        self.state = {
            "idea": idea, "iterations": total, "players": [p.to_dict() for p in players],
            "hits": [], "faults": [], "owner_notes": [], "next_side": 0,
            "current": None, "status": "running",
            "started_at": _now_ms(), "finished_at": None, "event_id": 0,
        }
        if start:
            self.start()

    def start(self):
        # A new rally must not overwrite the state behind an existing event stream.
        with (self.out / "events.jsonl").open("x", encoding="utf-8"):
            self.started = True
        self.save("serve", summary=f"Rally served: {self.state['iterations']} hits")

        set_active(self.out)

    def save(self, event=None, **details):
        if event:
            self.state["event_id"] += 1
        tmp = self.out / "state.json.tmp"
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.out / "state.json")
        if event:
            # Publish state first. A reader may see newer state, never older state.
            entry = {"id": self.state["event_id"], "type": event, "at": _now_ms(), **details}
            with (self.out / "events.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def set_active(out):
    ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ACTIVE.parent,
                                     prefix="active-", delete=False) as f:
        json.dump({"state": str(out / "state.json")}, f)
    os.replace(f.name, ACTIVE)


def _now_ms():
    return int(time.time() * 1000)


def load_state(directory=None):
    path = (pathlib.Path(directory) / "state.json" if directory else
            pathlib.Path(json.loads(ACTIVE.read_text(encoding="utf-8"))["state"]))
    return path.parent, json.loads(path.read_text(encoding="utf-8"))


def status_text(state):
    line = f"Rally {state['status']}: {len(state['hits'])}/{state['iterations']} turns completed."
    measured = drift_text(state["hits"][-1]) if state["hits"] else ""
    return f"{line} Last hit {measured}." if measured else line


def wait_for_event(directory=None, after=None, timeout=180):
    """Return one event, its latest committed state, and the command exit code.

    An explicit cursor drains the log in order. With no cursor, a running rally
    starts at the serve; a finished rally immediately reports its terminal event.
    """
    out, state = load_state(directory)
    log = out / "events.jsonl"
    if not log.is_file():
        raise ValueError(f"No event log in {out}; start a new rally with this version.")
    deadline = time.monotonic() + timeout
    while True:
        # Read the log first and state second: every complete line refers to an
        # already-published state revision. Ignore an in-progress final line.
        with log.open("rb") as f:
            events = [json.loads(line.decode("utf-8")) for line in f if line.endswith(b"\n")]
        _, state = load_state(out)
        events = [e for e in events if e["id"] <= state.get("event_id", 0)]
        candidates = [e for e in events if e["id"] > (after or 0)]
        if after is None and state["status"] != "running":
            candidates = [e for e in candidates if e["type"] in ("done", "error", "stopped")]
        if candidates:
            event = candidates[0]
            return event, state, 1 if event["type"] == "error" else 0
        if time.monotonic() >= deadline:
            return None, state, 2
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))


def watch_command(command, argv):
    ap = argparse.ArgumentParser(prog=f"rally.py {command}")
    ap.add_argument("--dir", help="rally directory (default: active rally)")
    if command == "wait":
        ap.add_argument("--after", type=int, help="last event ID; use 0 to read from the serve")
        ap.add_argument("--timeout", type=float, default=180, help="seconds to wait (default 180)")
    args = ap.parse_args(argv)
    if command == "wait" and (args.timeout < 0 or not math.isfinite(args.timeout)
                               or (args.after is not None and args.after < 0)):
        ap.error("--after and --timeout must be non-negative; timeout must be finite")
    try:
        if command == "status":
            _, state = load_state(args.dir)
            print(status_text(state))
            return 0
        event, state, code = wait_for_event(args.dir, args.after, args.timeout)
        print(status_text(state))
        if event:
            summary = " ".join(event.get("summary", "").split())
            print(f"event {event['id']}: {event['type']} | {summary}")
        else:
            print(f"timeout: no event after {args.after or 0}")
        return code
    except (OSError, ValueError, KeyError) as exc:
        print(f"Cannot read rally: {exc}", file=sys.stderr)
        return 1


def doctor(argv):
    """Probe both selected players with a small expected-format request."""
    ap = argparse.ArgumentParser(prog="rally.py doctor", description="Check installed player CLIs.")
    ap.add_argument("--players", help="two comma-separated player specs")
    args = ap.parse_args(argv)
    specs = [s.strip() for s in args.players.split(",")] if args.players else auto_pick(detect_players())
    if len(specs) != 2:
        if not specs:
            print("No player CLIs or API providers found. Set up two players; see PLAYERS.md.",
                  file=sys.stderr)
        else:
            print("Need exactly two players to preflight; see PLAYERS.md.", file=sys.stderr)
        return 1
    try:
        players = [Player(spec) for spec in specs]
    except ValueError as exc:
        print(f"Invalid player spec: {exc}", file=sys.stderr)
        return 1
    return 0 if preflight_players(players) else 1


def preflight_players(players):
    ok = True
    system = SYSTEM.format(me="preflight player", them="the other player", n=1, total=1,
                           remaining=0, phase=PHASES["close"], budget=1000)
    for player in players:
        try:
            started = time.monotonic()
            raw = player.call(system, 'Return this exact JSON: {"critique":"ok","version":"pong","changes":[],"open_questions":[]}')
            reply = parse_reply(raw)
            required = ('"critique"', '"version"', '"changes"', '"open_questions"')
            if (not reply["parsed"] or reply["version"] != "pong"
                    or not all(key in raw for key in required)):
                raise RuntimeError("player did not return the expected JSON response")
            print(f"preflight {player.spec}: ready ({time.monotonic() - started:.1f}s)")
        except Exception as exc:  # noqa: BLE001 - report setup problems before the rally
            ok = False
            print(f"preflight {player.spec}: failed: {exc}", file=sys.stderr)
    return ok


class Progress:
    """Plain process log; visual activity belongs to the optional widget."""
    def fly(self, n, total, side, expected_s):
        print(f"turn {n}/{total}: player {side + 1} working ...", flush=True)

    def land(self, message):
        print(message, flush=True)


# ---------------------------------------------------------------- main loop


@contextmanager
def rally_lock(out):
    """Hold an OS lock so a live rally cannot be resumed by another engine."""
    with (pathlib.Path(out) / "engine.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            acquire = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as exc:
            raise ValueError("rally already has an active engine; wait for it to stop") from exc
        try:
            yield
        finally:
            lock.seek(0)
            release()


def play(idea, total, players, out, ticker):
    with rally_lock(out):
        return _play(idea, total, players, out, ticker)


def _play(idea, total, players, out, ticker):
    rally = Rally(idea, total, players, out, start=False)
    try:
        rally.start()
        return play_turns(rally, idea, total, players, ticker)
    except KeyboardInterrupt:
        if not rally.started:
            raise
        rally.state.update(status="stopped", current=None, finished_at=_now_ms())
        rally.save("stopped", summary="Rally cancelled")
        return rally
    except Exception:
        if not rally.started:
            raise
        rally.state.update(status="error", current=None, finished_at=_now_ms())
        rally.save("error", summary="Rally interrupted by an engine error")
        write_outputs(rally)
        raise


def play_turns(rally, idea, total, players, ticker):
    hits = rally.state["hits"]
    prev = hits[-1] if hits else None
    current = rally.state.get("current") or {}
    side = current.get("side", rally.state.get("next_side", (prev["side"] ^ 1) if prev else 0))
    durations, consecutive_faults = [], 0
    n = len(hits) + 1
    while n <= total:
        me, them = players[side], players[1 - side]
        rally.state["current"] = {"n": n, "side": side, "started_at": _now_ms()}
        rally.save()
        expected = sum(durations) / len(durations) if durations else 30
        ticker.fly(n, total, side, expected)
        notes = consume_notes(rally)
        phase = phase_for(n, total)
        incoming_size = len(prev["version"]) if prev else max(120, len(idea))
        budget = size_budget(phase, incoming_size)
        system = SYSTEM.format(me=me.label, them=them.label, n=n, total=total,
                               remaining=remaining_iterations(n, total),
                               phase=PHASES[phase], budget=budget)
        prompt = user_prompt(idea, prev, them.label, notes)
        t0 = time.time()
        reply, err, fatal = None, None, False
        for attempt in range(2):
            try:
                reply = parse_reply(me.call(system, prompt))
                if not reply["parsed"]:
                    raise RuntimeError("unparseable player response (expected the JSON reply object)")
                break
            except Exception as e:  # noqa: BLE001 - surface any transport failure as a fault
                err = str(e)
                fatal = is_fatal_player_error(err)
                reply = None
                if fatal or attempt == 1:
                    break
                system += "\nReply with only the JSON object, including a non-empty version."
                time.sleep(5)
        if reply is not None:
            over_budget = len(reply["version"]) > budget
            if over_budget:
                ticker.land(f"  size limit: {me.label} returned {len(reply['version'])} characters; retrying within {budget}")
                retry_system = system + "\nYour previous version exceeded the character limit. Return the complete version again, cut to the stated maximum."
                try:
                    retry_user = prompt + "\n---\nYour previous over-budget version to revise:\n" + reply["version"]
                    retry = parse_reply(me.call(retry_system, retry_user))
                    if retry["parsed"]:
                        reply = retry
                        over_budget = len(reply["version"]) > budget
                except Exception as e:  # noqa: BLE001 - keep valid output unless the error is fatal
                    if is_fatal_player_error(str(e)):
                        err, fatal, reply = str(e), True, None
                    else:
                        ticker.land(f"  size-limit retry failed; keeping first valid reply: {e}")
        took = time.time() - t0
        if reply is None:
            consecutive_faults += 1
            rally.state["faults"].append({"n": n, "side": side, "player": me.label,
                                           "error": err, "fatal": fatal})
            rally.state["next_side"] = side if fatal else 1 - side
            rally.save("fault", n=n, side=side, summary=f"{me.label}: {err}")
            if fatal:
                rally.state["status"] = "error"
                rally.state["current"] = None
                rally.state["finished_at"] = _now_ms()
                rally.save("error", summary=f"Fatal player error; stopped immediately: {err}")
                ticker.land(f"  fatal error: stopping immediately; {me.label}: {err}")
                return rally
            ticker.land(f"  fault: {me.label} could not return hit {n}: {err}")
            if consecutive_faults >= 2:
                rally.state["next_side"] = side
                rally.state["status"] = "error"
                rally.state["current"] = None
                rally.state["finished_at"] = _now_ms()
                rally.save("error", summary="Rally stopped after two consecutive faults")
                ticker.land("  stopping: both players failed consecutive turns; partial result is saved")
                return rally
            side = rally.state["next_side"]  # opponent takes the hit
            continue
        consecutive_faults = 0
        durations.append(took)
        hit = {"n": n, "side": side, "player": me.label, "seconds": round(took, 1), **reply,
               "phase": phase, "size_budget": budget, "over_budget": over_budget,
               **drift(prev["version"] if prev else None, reply["version"])}
        rally.state["hits"].append(hit)
        rally.state["current"] = None
        rally.state["next_side"] = 1 - side
        rally.save("hit", n=n, side=side, summary=f"Hit {n}/{total} by {me.label}")
        measured = drift_text(hit)
        ticker.land(f"  hit {n}/{total} by {me.label} in {took:.0f}s"
                    + (f": {hit['changes'][0]}" if hit["changes"] else "")
                    + (f" [{measured}]" if measured else ""))
        prev, side, n = hit, 1 - side, n + 1
    rally.state["status"] = "done"
    rally.state["current"] = None
    rally.state["finished_at"] = _now_ms()
    rally.save("done", summary=f"Rally finished: {len(rally.state['hits'])} hits")
    return rally


def is_fatal_player_error(message):
    """Identify errors that cannot be fixed by retrying or switching players."""
    value = message.lower().replace("_", " ").replace("-", " ")
    phrases = (
        "token limit", "max tokens", "context limit", "context length", "context window",
        "maximum context", "prompt is too long", "input is too long", "too many tokens",
        "maximum number of tokens", "token count exceeds", "input token limit",
        "request too large", "maximum input", "authentication", "unauthorized",
        "not logged in", "api key", "unknown model", "model not found", "not on path",
        "no such file or directory", "unknown option", "unrecognized option", "unknown flag",
    )
    return any(phrase in value for phrase in phrases) or (
        "token" in value and ("maximum" in value or "limit" in value))


def consume_notes(rally):
    inbox = rally.out / "inbox"
    inbox.mkdir(exist_ok=True)
    seen = rally.state.setdefault("owner_notes", [])
    for item in sorted(inbox.glob("*.md")):
        note = item.read_text(encoding="utf-8").strip()
        if note:
            seen.append(note)
            rally.save("note", summary="Owner note received", note=note)
        item.unlink(missing_ok=True)
    return list(rally.state["owner_notes"])


def append_note(directory, note):
    note = note.strip()
    if not note:
        raise ValueError("note cannot be empty")
    out, state = load_state(directory)
    if state.get("status") != "running":
        raise ValueError(f"rally is {state.get('status')}; notes can only be added while it is running")
    inbox = out / "inbox"
    inbox.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=inbox,
                                     prefix=f"note-{time.time_ns():020d}-", suffix=".tmp", delete=False) as f:
        f.write(note)
        temporary = pathlib.Path(f.name)
    os.replace(temporary, inbox / (temporary.stem + ".md"))
    print(f"Note queued for the next hit in {out}.")


def resume_command(argv):
    ap = argparse.ArgumentParser(prog="rally.py resume", description="Resume an interrupted rally.")
    ap.add_argument("--dir", help="rally directory (default: active rally)")
    args = ap.parse_args(argv)
    try:
        out, _ = load_state(args.dir)
        with rally_lock(out):
            return resume_rally(out)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Cannot resume rally: {exc}", file=sys.stderr)
        return 1


def resume_rally(out):
    # Reload after acquiring the lock; another engine may have just finished.
    out, state = load_state(out)
    if state.get("status") == "done":
        raise ValueError("rally is already complete")
    if len(state.get("hits", [])) >= state.get("iterations", 0):
        raise ValueError("rally has no unfinished iterations")
    players = [Player(p["spec"]) for p in state["players"]]
    if not preflight_players(players):
        print("Resume stopped: player preflight failed. Fix the issue, then try again.", file=sys.stderr)
        return 1
    rally = Rally.__new__(Rally)
    rally.out, rally.state, rally.started = out, state, True
    rally.state["status"] = "running"
    rally.state["finished_at"] = None
    rally.save("resume", summary=f"Resuming at hit {len(state['hits']) + 1}/{state['iterations']}")
    set_active(out)
    previous_term = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        rally = play_turns(rally, state["idea"], state["iterations"], players, Progress())
    except KeyboardInterrupt:
        rally.state.update(status="stopped", current=None, finished_at=_now_ms())
        rally.save("stopped", summary="Rally paused by user")
    except Exception as exc:  # noqa: BLE001 - preserve partial work
        rally.state.update(status="error", current=None, finished_at=_now_ms())
        rally.save("error", summary=f"Engine error: {exc}")
        print(f"Rally stopped after an engine error: {exc}", file=sys.stderr)
    finally:
        signal.signal(signal.SIGTERM, previous_term)
    write_outputs(rally)
    print(f"status: {rally.state['status']}")
    print(f"final: {out / 'final.md'}")
    return 0 if rally.state["status"] == "done" else 130 if rally.state["status"] == "stopped" else 1


def write_outputs(rally):
    s, out = rally.state, rally.out
    lines = []
    if s["hits"]:
        last = s["hits"][-1]
        questions = []
        for h in s["hits"]:
            for q in h["open_questions"]:
                if q not in questions:
                    questions.append(q)
        lines = [last["version"].rstrip(), "", "---", "",
                 f"Rally: {len(s['hits'])}/{s['iterations']} hits between "
                 + " and ".join(p["label"] for p in s["players"]) + "."]
        over = [h for h in s["hits"] if h.get("over_budget")]
        if over:
            lines += ["", "Size limit retries that remained over budget: "
                      + ", ".join(str(h["n"]) for h in over) + "."]
        if questions:
            lines += ["", "Open questions raised during the rally:"] + [f"- {q}" for q in questions]
        conflicts = [c for h in s["hits"] for c in h.get("owner_conflicts", [])]
        if conflicts:
            lines += ["", "Owner requirements agents proposed changing:"]
            lines += [f"- {c.get('item', 'requirement')}: {c.get('reason', 'no reason supplied')}"
                      for c in conflicts]
    else:
        lines = ["# Ping-pong rally", "", "No completed turns yet."]
    lines += ["", f"Status: {s['status']}."]
    if s.get("faults"):
        lines += ["", "Player errors:"]
        lines += [f"- Hit {f['n']}, {f['player']}: {f['error']}" for f in s["faults"]]
    if s.get("owner_notes"):
        lines += ["", "Owner notes carried through the rally:"]
        lines += [f"- {note}" for note in s["owner_notes"]]
    (out / "final.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    from animation import animation_command, animation_enabled, serve_animation
    if len(sys.argv) > 1 and sys.argv[1] == "animation":
        return animation_command(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] in ("status", "wait"):
        return watch_command(sys.argv[1], sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "resume":
        return resume_command(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "note":
        note_ap = argparse.ArgumentParser(prog="rally.py note", description="Queue an owner note for the next hit.")
        note_ap.add_argument("--dir", help="rally directory (default: active rally)")
        note_ap.add_argument("text", nargs="+", help="the note to add")
        note_args = note_ap.parse_args(sys.argv[2:])
        try:
            append_note(note_args.dir, " ".join(note_args.text))
            return 0
        except (OSError, ValueError, KeyError) as exc:
            print(f"Cannot add note: {exc}", file=sys.stderr)
            return 1
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        return doctor(sys.argv[2:])
    ap = argparse.ArgumentParser(description="Bounce an idea between two LLMs.")
    ap.add_argument("--idea", help="the idea as text")
    ap.add_argument("--idea-file", help="read the idea from a file")
    ap.add_argument("-n", "--iterations", type=int, default=10, help="number of hits (default 10)")
    ap.add_argument("--players", help="two comma-separated specs, e.g. cli:claude,cli:codex")
    ap.add_argument("--out", help="rally directory (default ./.ping-pong/<timestamp>-<slug>)")
    display = ap.add_mutually_exclusive_group()
    display.add_argument("--animation", action="store_true", help="expose the embeddable pixel widget locally")
    display.add_argument("--no-animation", action="store_true", help="disable animation for this rally")
    ap.add_argument("--list-players", action="store_true")
    a = ap.parse_args()

    if a.list_players:
        found = detect_players()
        print("detected:", ", ".join(found) or "nothing")
        print("auto pick:", ", ".join(auto_pick(found)) or "none")
        return 0

    idea = pathlib.Path(a.idea_file).read_text(encoding="utf-8") if a.idea_file else a.idea
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
    if not preflight_players(players):
        print("Rally not started: player preflight failed. Fix the issue or choose different players.",
              file=sys.stderr)
        return 1

    slug = re.sub(r"[^a-z0-9]+", "-", idea.lower())[:32].strip("-") or "idea"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if a.out:
        out = pathlib.Path(a.out).resolve()
        out.mkdir(parents=True, exist_ok=True)
    else:
        base = pathlib.Path(".ping-pong").resolve()
        base.mkdir(parents=True, exist_ok=True)
        out = pathlib.Path(tempfile.mkdtemp(prefix=f"{stamp}-{slug}-", dir=base))
    if (out / "state.json").exists() or (out / "events.jsonl").exists():
        ap.error(f"rally already exists in {out}; choose a new --out directory")
    srv = None
    if a.animation and animation_enabled():
        try:
            srv = serve_animation(out)
            print(f"animation: http://127.0.0.1:{srv.server_port}/", flush=True)
        except OSError as exc:
            print(f"Animation unavailable ({exc}); rally continues.", file=sys.stderr)

    print(f"rally: {players[0].label} vs {players[1].label}, {a.iterations} hits", flush=True)
    print(f"dir: {out}", flush=True)
    previous_term = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        try:
            rally = play(idea.strip(), a.iterations, players, out, Progress())
        except Exception as exc:  # noqa: BLE001 - leave and report any partial artifact
            print(f"Rally stopped by an engine error: {exc}", file=sys.stderr)
            if (out / "final.md").exists():
                print(f"partial result: {out / 'final.md'}", file=sys.stderr)
            return 1
        write_outputs(rally)
        print(f"status: {rally.state['status']}", flush=True)
        if (out / "final.md").exists():
            print(f"final: {out / 'final.md'}", flush=True)
        return 0 if rally.state["status"] == "done" else 130 if rally.state["status"] == "stopped" else 1
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        if srv:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    sys.exit(main())
