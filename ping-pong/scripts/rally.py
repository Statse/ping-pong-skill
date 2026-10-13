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

HERE = pathlib.Path(__file__).resolve().parent
# The three supported agent CLIs, in detection order. The default pair is Claude then
# Codex; `mock` stays available for credential-free development.
CLI_LABELS = {"claude": "Claude Code", "codex": "Codex", "cursor": "Cursor"}
SUPPORTED_CLIS = tuple(CLI_LABELS)
DEFAULT_PAIR = ("cli:claude", "cli:codex")
ACTIVE = pathlib.Path.home() / ".ping-pong" / "active.json"
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
LEDGER_CAP = 25          # entries rendered into a prompt; owner entries are never evicted
BULLET = re.compile(r"^\s*[-*+]\s*")


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
                raise ValueError(f"cli player needs a tool name: {spec}; "
                                 f"supported: {supported_specs()}")
            self.tool = parts[1]
            if self.tool not in CLI_LABELS:
                raise ValueError(f"unsupported CLI '{self.tool}' in {spec}; "
                                 f"supported: {supported_specs()}")
            self.model = parts[2] if len(parts) > 2 else None
            base = CLI_LABELS[self.tool]
        elif self.kind == "mock":
            self.tool, self.model = None, None
            base = f"Mock {parts[1] if len(parts) > 1 else ''}".strip()
        else:
            raise ValueError(f"unknown player kind '{self.kind}' in {spec}; "
                             f"supported: {supported_specs()}")
        self.label = f"{base} ({self.model})" if self.kind == "cli" and self.model else base

    def to_dict(self):
        return {"spec": self.spec, "label": self.label}

    def call(self, system, user):
        if self.kind == "mock":
            return _mock(system, user)
        return _cli(self.tool, self.model, system, user)


def supported_specs():
    return ", ".join("cli:%s" % tool for tool in SUPPORTED_CLIS)


def detect_players():
    """Installed supported CLIs. API keys never affect detection or selection."""
    return [f"cli:{tool}" for tool in SUPPORTED_CLIS if cli_bin(tool)]


def auto_pick(found):
    """The default pair when it is installed, otherwise two detected CLIs.

    Never substitutes a model alias and never pairs one CLI with itself: two
    sessions of the same CLI are a valid rally, but only as an explicit choice.
    """
    if all(spec in found for spec in DEFAULT_PAIR):
        return list(DEFAULT_PAIR)
    return found[:2]


def missing_players_message(found):
    """Why no pair could be chosen, and what the user can do about it."""
    missing = ", ".join(CLI_LABELS[spec.split(":")[1]] for spec in DEFAULT_PAIR
                        if spec not in found)
    lines = ["Detected: " + (", ".join(found) or "no supported player CLI")]
    if missing:
        lines.append(f"The default pair is Claude then Codex; not installed: {missing}.")
    lines.append("Install a second supported CLI (%s), or choose a pair with"
                 " --players, e.g. --players %s,%s for two independent sessions of"
                 " the same CLI. See PLAYERS.md."
                 % (supported_specs(), found[0] if found else DEFAULT_PAIR[0],
                    found[0] if found else DEFAULT_PAIR[0]))
    return "\n".join(lines)


# ---------------------------------------------------------------- transports


def _cli(tool, model, system, user):
    prompt = f"{system}\n\n---\n\n{user}"
    exe = cli_bin(tool)
    if not exe:
        raise RuntimeError(f"'{tool}' is not on PATH")
    workdir = tempfile.mkdtemp(prefix="pingpong-")  # keep agent CLIs away from the user's repo
    out_file = os.path.join(workdir, "last.txt")
    m = lambda flag: [flag, model] if model else []
    if tool == "claude":
        cmd = [exe] + m("--model") + ["-p", prompt]
    elif tool == "codex":
        cmd = [exe, "exec", "--skip-git-repo-check", "--output-last-message", out_file] + m("-m") + [prompt]
    elif tool == "cursor":
        cmd = [exe, "-p", "--trust", "--mode", "ask", "--output-format", "text"] + m("--model") + [prompt]
    else:
        raise RuntimeError(f"unsupported CLI '{tool}'; supported: {supported_specs()}")
    try:
        try:
            p = run_cli(cmd, None, workdir, timeout=1800)
        except subprocess.TimeoutExpired as exc:
            # TimeoutExpired includes argv (and hence the whole prompt) in str().
            # Keep user content out of the diagnostic used for fatal classification.
            raise RuntimeError(f"{tool} timed out after {exc.timeout} seconds") from exc
        if p.returncode != 0:
            raise RuntimeError(
                f"{tool} exited {p.returncode}: "
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
- Review the previous hit's open questions and requirement conflicts. Carry unresolved ones forward; do not invent owner answers or treat a proposed change as approval.
- Honour the decision ledger in the prompt. `O-*` entries are owner non-negotiables: you cannot drop them, only report a conflict. Add a `P-*` decision for anything you commit to, and drop one only with a reason.
- Your version must stand alone: someone who reads only it gets the whole idea.
- Write in the language of the owner's original idea.
- If the brief asks for a particular output form, language, audience or length, follow it in your version; those instructions outrank your own preference. Without such a request, return a refined idea, not a build prompt or a ticket spec.

Reply with only this JSON object:
{{"critique": "honest, specific notes on the incoming version",
 "version": "the full improved idea, markdown allowed",
 "changes": ["one short line per change you made"],
 "open_questions": ["questions only the idea's owner can answer"],
 "owner_conflicts": [{{"item": "owner requirement", "reason": "why it should change"}}],
 "decisions": [{{"op": "add", "text": "a decision this version commits to"}},
               {{"op": "drop", "id": "P-2", "reason": "why it no longer holds"}}]}}"""

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


# Live rallies never needed more than 4.5x the served version, over ten hits from
# a one-sentence brief; four-hit rallies needed 1.4x to 2.9x. See
# `docs/evidence/live-validation-2026-10-13.md`.
GROWTH_CEILING = 5


def size_budget(phase, incoming_size, anchor=None):
    """Maximum version size for a phase, measured against the incoming draft.

    The phase multiplier is relative, so on its own the allowance ratchets with
    the hit count: 11.7x the served version over ten compliant hits, and about
    137x over twenty. `anchor` is the served version's size, and it caps that
    ratchet at `GROWTH_CEILING` without compounding. A draft that already sits at
    the ceiling can still be rewritten; it is never asked to shrink.
    """
    multiplier = {"open": 1.6, "deepen": 1.3, "close": 1.0}[phase]
    budget = max(1, int(incoming_size * multiplier))
    if anchor:
        budget = min(budget, max(incoming_size, int(anchor * GROWTH_CEILING)))
    return budget


def seed_owner_ledger(out):
    """Owner non-negotiables from constraints.md. A missing or empty file is valid."""
    try:
        text = (pathlib.Path(out) / "constraints.md").read_text(encoding="utf-8")
    except OSError:
        return []
    entries = []
    for line in text.splitlines():
        item = BULLET.sub("", line).strip()
        if item:
            entries.append({"id": "O-%d" % (len(entries) + 1), "by": "owner",
                            "text": item, "status": "standing", "reason": None})
    return entries


def new_rally_dir(idea, requested=None):
    """A directory with no rally in it yet. The host may name it instead of guessing."""
    # abspath, not resolve: Windows resolve() can hand back a relative path for a
    # directory that does not exist yet, and the host has to be able to use what we print.
    if requested:
        out = pathlib.Path(os.path.abspath(requested))
        out.mkdir(parents=True, exist_ok=True)
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", (idea or "").lower())[:32].strip("-") or "idea"
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        base = pathlib.Path(os.path.abspath(".ping-pong"))
        base.mkdir(parents=True, exist_ok=True)
        out = pathlib.Path(tempfile.mkdtemp(prefix=f"{stamp}-{slug}-", dir=base))
    out = out.resolve()  # safe now that the directory exists
    if (out / "state.json").exists() or (out / "events.jsonl").exists():
        raise ValueError(f"rally already exists in {out}; choose a new directory")
    return out


def write_constraints(out, constraints):
    """Seed constraints.md with the owner's explicit non-negotiables, one per bullet.

    No constraints means no file: an idea without explicit non-negotiables must run
    with an empty owner ledger rather than with inferred requirements.
    """
    items = [" ".join(c.split()) for c in constraints if c and c.strip()]
    if not items:
        return []
    path = pathlib.Path(out) / "constraints.md"
    if path.exists():
        raise ValueError(f"{path} already exists; edit it instead of reseeding")
    path.write_text("".join("- %s\n" % item for item in items), encoding="utf-8")
    return items


def setup_command(argv):
    ap = argparse.ArgumentParser(
        prog="rally.py setup",
        description="Prepare a fresh rally directory and seed owner constraints.")
    ap.add_argument("--idea", help="the idea, used only to name the directory")
    ap.add_argument("--idea-file", help="read the naming idea from a file")
    ap.add_argument("--out", help="use this directory instead of a generated name")
    ap.add_argument("--constraint", action="append", default=[], metavar="TEXT",
                    help="an explicit owner non-negotiable; repeat for each one")
    a = ap.parse_args(argv)
    try:
        idea = pathlib.Path(a.idea_file).read_text(encoding="utf-8") if a.idea_file else (a.idea or "")
        out = new_rally_dir(idea, a.out)
        write_constraints(out, a.constraint)
    except (OSError, ValueError) as exc:
        print(f"Cannot prepare a rally directory: {exc}", file=sys.stderr)
        return 1
    # Only the path on stdout, so the host can capture it and pass it to --out.
    print(out)
    return 0


def ledger_view(ledger, cap=LEDGER_CAP):
    """Entries to render, plus whether owner entries alone exceed the cap.

    Eviction is a rendering decision only: the oldest player entries drop out
    of the prompt first, owner entries never do, and state keeps everything.
    """
    owner = [e for e in ledger if e.get("by") == "owner"]
    others = [e for e in ledger if e.get("by") != "owner"]
    room = cap - len(owner)
    keep = {e["id"] for e in owner}
    keep.update(e["id"] for e in (others[-room:] if room > 0 else []))
    return [e for e in ledger if e["id"] in keep], len(owner) > cap


def render_ledger(ledger, cap=LEDGER_CAP):
    """The compact ledger as it reaches a player."""
    shown, over_cap = ledger_view(ledger, cap)
    lines = ["Decision ledger (carried through the whole rally). O-* entries are owner",
             "non-negotiables and cannot be dropped; dropping a P-* entry requires a reason:"]
    if not shown:
        lines.append("- (empty: no decisions recorded yet)")
    for entry in shown:
        by = "owner" if entry.get("by") == "owner" else str(entry.get("by") or "player")
        mark = ("" if entry.get("status") == "standing"
                else " [dropped: %s]" % (entry.get("reason") or "no reason recorded"))
        lines.append("- {0} ({1}): {2}{3}".format(entry["id"], by, entry.get("text", ""), mark))
    if over_cap:
        lines.append("Cap exception: owner entries alone exceed the %d-entry ledger cap, so every"
                     " owner entry is listed above and player entries are omitted." % cap)
    elif len(shown) < len(ledger):
        lines.append("%d older player entries are omitted to stay within the %d-entry cap;"
                     " they remain recorded." % (len(ledger) - len(shown), cap))
    return "\n".join(lines)


def user_prompt(idea, prev, them, owner_notes=None, ledger=None):
    head = ("Original brief from the owner, including any instruction about form, language,"
            f" audience or length:\n\n{idea}\n")
    if owner_notes:
        head += "\nOwner notes (these are authoritative and persist for the rest of the rally):\n"
        head += "\n".join(f"- {note}" for note in owner_notes) + "\n"
    if ledger is not None:
        head += "\n" + render_ledger(ledger) + "\n"
    if prev is None:
        return head + "\nYou serve: there is no previous version yet. Write the first version."
    changes = "\n".join(f"- {c}" for c in prev["changes"]) or "- (none listed)"
    questions = "\n".join(f"- {q}" for q in prev.get("open_questions", [])) or "- (none listed)"
    conflicts = "\n".join(
        f"- {c.get('item', 'requirement')}: {c.get('reason', 'no reason supplied')}"
        for c in prev.get("owner_conflicts", [])) or "- (none listed)"
    return (f"{head}\n---\nCurrent version (from {them}, hit {prev['n']}):\n\n{prev['version']}\n"
            f"\n---\n{them}'s notes on the version before:\n{prev['critique'] or '(none)'}\n"
            f"\nChanges {them} made:\n{changes}\n"
            f"\nOpen questions from the previous hit (carry forward if unresolved):\n{questions}\n"
            "\nRequirement conflicts from the previous hit (proposals, not owner approval;"
            f" preserve the requirements):\n{conflicts}\n")


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
            if (not isinstance(d, dict) or not isinstance(d.get("version"), str)
                    or not d["version"].strip()):
                continue
            critique = d.get("critique", "")
            changes = d.get("changes", [])
            questions = d.get("open_questions", [])
            conflicts = d.get("owner_conflicts", [])
            if not isinstance(critique, str):
                continue
            if any(not isinstance(items, list) or any(not isinstance(x, str) for x in items)
                   for items in (changes, questions)):
                continue
            if (not isinstance(conflicts, list) or any(
                    not isinstance(x, dict)
                    or any(not isinstance(x.get(key), str) or not x[key].strip()
                           for key in ("item", "reason")) for x in conflicts)):
                continue
            return {"critique": critique, "version": d["version"],
                    "changes": changes, "open_questions": questions,
                    "owner_conflicts": conflicts,
                    # Ledger junk remains non-fatal under the existing contract.
                    "decisions": ledger_ops(d.get("decisions")), "parsed": True}
        except (ValueError, TypeError):
            continue
    return {"critique": "", "version": text.strip(), "changes": [], "open_questions": [],
            "decisions": [], "parsed": False}


def ledger_ops(raw):
    """Usable ledger operations from a reply. Junk is ignored, never fatal."""
    operations = []
    if not isinstance(raw, list):
        return operations
    for item in raw:
        if not isinstance(item, dict) or item.get("op") not in ("add", "drop"):
            continue
        operations.append({"op": item["op"],
                           "id": str(item.get("id") or "").strip(),
                           "text": str(item.get("text") or "").strip(),
                           "reason": str(item.get("reason") or "").strip()})
    return operations


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
        self.error = None
        self.state = {
            "idea": idea, "iterations": total, "players": [p.to_dict() for p in players],
            "hits": [], "faults": [], "owner_notes": [], "consumed_notes": [],
            "next_side": 0,
            "ledger": seed_owner_ledger(out), "disputes": [],
            "current": None, "status": "running",
            "started_at": _now_ms(), "finished_at": None, "event_id": 0,
        }
        if start:
            self.start()

    @classmethod
    def load(cls, out, state):
        """A rally restored from its saved state: the supported path for resume.

        Construction must not re-seed the ledger or reset the event stream, so a
        loaded rally skips __init__ rather than reconstructing its state.
        """
        rally = cls.__new__(cls)
        rally.out, rally.state, rally.started, rally.error = pathlib.Path(out), state, True, None
        # Keep the ledger a resumed rally already has; never re-seed it.
        for key, default in (("hits", []), ("faults", []), ("owner_notes", []),
                             ("consumed_notes", []), ("ledger", []), ("disputes", [])):
            rally.state.setdefault(key, default)
        return rally

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
        publish(tmp, self.out / "state.json")
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
    publish(f.name, ACTIVE)


# Windows refuses to rename over a destination another process holds open, so an
# owner running `status`, `wait`, or `note` against a live rally could kill it
# with "[WinError 5] Access is denied". Every reader here opens the file for one
# short read, so a bounded retry outlasts the contention; POSIX never retries.
PUBLISH_ATTEMPTS = 20
PUBLISH_DELAY_S = 0.05


def publish(staged, destination):
    """Move a staged file over its destination. All-or-nothing for any reader."""
    for remaining in range(PUBLISH_ATTEMPTS - 1, -1, -1):
        try:
            os.replace(staged, destination)
            return
        except PermissionError as exc:
            if not remaining:
                raise OSError(
                    f"Could not publish {destination} after {PUBLISH_ATTEMPTS} attempts "
                    f"over {PUBLISH_ATTEMPTS * PUBLISH_DELAY_S:.1f}s; another process may "
                    f"be holding it open: {exc}") from exc
            time.sleep(PUBLISH_DELAY_S)


def _now_ms():
    return int(time.time() * 1000)


def load_state(directory=None):
    path = (pathlib.Path(directory) / "state.json" if directory else
            pathlib.Path(json.loads(ACTIVE.read_text(encoding="utf-8"))["state"]))
    return path.parent, json.loads(path.read_text(encoding="utf-8"))


def status_text(state):
    line = f"Rally {state['status']}: {len(state['hits'])}/{state['iterations']} turns completed."
    measured = drift_text(state["hits"][-1]) if state["hits"] else ""
    if measured:
        line += f" Last hit {measured}."
    standing = sum(1 for entry in state.get("ledger") or [] if entry.get("status") == "standing")
    return f"{line} Ledger: {standing} standing." if standing else line


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
    found = detect_players()
    specs = [s.strip() for s in args.players.split(",")] if args.players else auto_pick(found)
    if len(specs) != 2:
        if not args.players:
            print("No player CLIs found to preflight.", file=sys.stderr)
            print(missing_players_message(found), file=sys.stderr)
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
    def fly(self, n, total, side):
        print(f"turn {n}/{total}: player {side + 1} working ...", flush=True)

    def land(self, message):
        print(message, flush=True)


# ---------------------------------------------------------------- main loop


@contextmanager
def terminate_as_cancel():
    """Treat SIGTERM as a cancellation so a killed engine still finalizes."""
    def cancel(*_):
        raise KeyboardInterrupt()

    previous = signal.signal(signal.SIGTERM, cancel)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


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


def conclude(rally, status, summary):
    """Record a terminal state once, in one place, for every exit path."""
    rally.state.update(status=status, current=None, finished_at=_now_ms())
    rally.save(status, summary=summary)


def execute(rally, players, ticker, cancelled="Rally cancelled"):
    """Play the remaining turns under one cancellation and error policy.

    New and resumed rallies share this path, so both end in a terminal state
    with a usable `final.md`, including before the first completed hit. An engine
    error is recorded on the rally rather than raised: the caller reports it.

    A rally that never got as far as its own event stream has no state to
    finalize, so that failure is raised for the caller to report instead.
    """
    try:
        if not rally.started:
            rally.start()
        play_turns(rally, rally.state["idea"], rally.state["iterations"], players, ticker)
    except KeyboardInterrupt:
        if not rally.started:
            raise
        conclude(rally, "stopped", cancelled)
    except Exception as exc:  # noqa: BLE001 - preserve partial work, then report
        if not rally.started:
            raise
        rally.state["error"] = str(exc)
        conclude(rally, "error", f"Engine error: {exc}")
        rally.error = exc
    write_outputs(rally)
    return rally


def report_result(rally, stream=sys.stdout):
    """The shared end-of-run report and exit code for starting and resuming."""
    print(f"status: {rally.state['status']}", file=stream, flush=True)
    final = rally.out / "final.md"
    if final.exists():
        print(f"final: {final}", file=stream, flush=True)
    return {"done": 0, "stopped": 130}.get(rally.state["status"], 1)


def play(idea, total, players, out, ticker):
    """Start and run a new rally. Raises only if it never started."""
    with rally_lock(out):
        return execute(Rally(idea, total, players, out, start=False), players, ticker)


def fetch_reply(me, system, prompt, budget, ticker):
    """One player's valid, budget-adjusted reply for a single hit.

    This owns the whole request policy: one retry for an unparsed reply after a
    JSON reminder, one rewrite attempt for an over-budget version, and no retry
    at all for a fatal error. The rally loop owns which player hits and what is
    committed. Returns `(reply, error, fatal, over_budget)` with `reply` None
    when the hit could not be obtained.
    """
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
    if reply is None:
        return None, err, fatal, False
    over_budget = len(reply["version"]) > budget
    if not over_budget:
        return reply, err, fatal, False
    ticker.land(f"  size limit: {me.label} returned {len(reply['version'])} characters; retrying within {budget}")
    retry_system = system + "\nYour previous version exceeded the character limit. Return the complete version again, cut to the stated maximum."
    retry_user = prompt + "\n---\nYour previous over-budget version to revise:\n" + reply["version"]
    try:
        retry = parse_reply(me.call(retry_system, retry_user))
        if retry["parsed"]:
            reply = retry
            over_budget = len(reply["version"]) > budget
    except Exception as e:  # noqa: BLE001 - keep valid output unless the error is fatal
        if is_fatal_player_error(str(e)):
            return None, str(e), True, False
        ticker.land(f"  size-limit retry failed; keeping first valid reply: {e}")
    return reply, err, fatal, over_budget


def play_turns(rally, idea, total, players, ticker):
    hits = rally.state["hits"]
    prev = hits[-1] if hits else None
    current = rally.state.get("current") or {}
    side = current.get("side", rally.state.get("next_side", (prev["side"] ^ 1) if prev else 0))
    consecutive_faults = 0
    n = len(hits) + 1
    while n <= total:
        me, them = players[side], players[1 - side]
        rally.state["current"] = {"n": n, "side": side, "started_at": _now_ms()}
        rally.save()
        ticker.fly(n, total, side)
        notes = consume_notes(rally)
        phase = phase_for(n, total)
        incoming_size = len(prev["version"]) if prev else max(120, len(idea))
        # The serve anchors the ceiling; before it exists there is nothing to ratchet.
        anchor = len(hits[0]["version"]) if hits else None
        budget = size_budget(phase, incoming_size, anchor)
        system = SYSTEM.format(me=me.label, them=them.label, n=n, total=total,
                               remaining=remaining_iterations(n, total),
                               phase=PHASES[phase], budget=budget)
        prompt = user_prompt(idea, prev, them.label, notes, rally.state.setdefault("ledger", []))
        t0 = time.time()
        reply, err, fatal, over_budget = fetch_reply(me, system, prompt, budget, ticker)
        took = time.time() - t0
        if reply is None:
            consecutive_faults += 1
            rally.state["faults"].append({"n": n, "side": side, "player": me.label,
                                           "error": err, "fatal": fatal})
            rally.state["next_side"] = side if fatal else 1 - side
            rally.save("fault", n=n, side=side, summary=f"{me.label}: {err}")
            if fatal:
                conclude(rally, "error", f"Fatal player error; stopped immediately: {err}")
                ticker.land(f"  fatal error: stopping immediately; {me.label}: {err}")
                return rally
            ticker.land(f"  fault: {me.label} could not return hit {n}: {err}")
            if consecutive_faults >= 2:
                rally.state["next_side"] = side
                conclude(rally, "error", "Rally stopped after two consecutive faults")
                ticker.land("  stopping: both players failed consecutive turns; partial result is saved")
                return rally
            side = rally.state["next_side"]  # opponent takes the hit
            continue
        consecutive_faults = 0
        hit = {"n": n, "side": side, "player": me.label, "seconds": round(took, 1), **reply,
               "phase": phase, "size_budget": budget, "over_budget": over_budget,
               **drift(prev["version"] if prev else None, reply["version"])}
        rally.state["hits"].append(hit)
        rally.state["current"] = None
        rally.state["next_side"] = 1 - side
        # Fold this hit's ledger changes into the same atomic write as the hit, so a
        # crash can never leave a completed hit whose decisions were not recorded.
        applied = apply_decisions(rally, n, me.label, reply.get("decisions"))
        rally.save("hit", n=n, side=side, summary=f"Hit {n}/{total} by {me.label}")
        save_ledger_event(rally, applied)
        for record in applied["disputed"]:
            ticker.land("  ledger: refused {0} of {1} ({2})".format(
                record["op"], record["id"] or "an entry", record["refused"]))
        measured = drift_text(hit)
        ticker.land(f"  hit {n}/{total} by {me.label} in {took:.0f}s"
                    + (f": {hit['changes'][0]}" if hit["changes"] else "")
                    + (f" [{measured}]" if measured else ""))
        prev, side, n = hit, 1 - side, n + 1
    conclude(rally, "done", f"Rally finished: {len(rally.state['hits'])} hits")
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


def next_player_id(ledger):
    used = [0]
    for entry in ledger:
        identifier = str(entry.get("id", ""))
        if identifier.startswith("P-") and identifier[2:].isdigit():
            used.append(int(identifier[2:]))
    return "P-%d" % (max(used) + 1)


def apply_decisions(rally, n, player, decisions):
    """Apply one hit's ledger operations to state. Nothing here faults the rally.

    This only mutates state, so the caller can fold the changes into the same
    atomic write as the hit itself and then announce them with save_ledger_event.
    Refused and rejected operations become disputes so the owner can see what a
    player wanted to remove; the targeted entry itself is left untouched.
    """
    ledger = rally.state.setdefault("ledger", [])
    disputes = rally.state.setdefault("disputes", [])
    by_id = {str(entry.get("id")): entry for entry in ledger}
    added, dropped, refused = [], [], []

    def dispute(operation, target, reason, why):
        record = {"n": n, "player": player, "op": operation, "id": target,
                  "reason": reason, "refused": why}
        disputes.append(record)
        refused.append(record)

    for item in decisions or []:
        if item["op"] == "add":
            if not item["text"]:
                dispute("add", item["id"], item["reason"], "an added decision needs text")
                continue
            entry = {"id": next_player_id(ledger), "by": player, "text": item["text"],
                     "status": "standing", "reason": None}
            ledger.append(entry)
            by_id[entry["id"]] = entry
            added.append(entry["id"])
            continue
        target, reason = item["id"], item["reason"]
        entry = by_id.get(target)
        if not reason:
            dispute("drop", target, reason, "a drop requires a reason")
        elif target.startswith("O-") or (entry is not None and entry.get("by") == "owner"):
            dispute("drop", target, reason, "owner non-negotiables cannot be dropped")
        elif entry is None:
            dispute("drop", target, reason, "no such ledger entry")
        elif entry.get("status") != "standing":
            dispute("drop", target, reason, "entry was already dropped")
        else:
            entry["status"] = "dropped"
            entry["reason"] = reason
            dropped.append(target)

    return {"n": n, "added": added, "dropped": dropped, "disputed": refused}


def save_ledger_event(rally, applied):
    """Announce ledger changes already written into state by apply_decisions."""
    if not (applied["added"] or applied["dropped"] or applied["disputed"]):
        return
    summary = "Ledger after hit %d: %d added, %d dropped, %d disputed" % (
        applied["n"], len(applied["added"]), len(applied["dropped"]), len(applied["disputed"]))
    rally.save("ledger", n=applied["n"], summary=summary, added=applied["added"],
               dropped=applied["dropped"],
               disputed=[dict(record) for record in applied["disputed"]])


# Owner notes are identified by an inbox sequence number, not by a timestamp: a clock
# too coarse to separate two quick submissions must not reorder them.
NOTE_SEQ_WIDTH = 9


def note_name(seq):
    return "note-%0*d.md" % (NOTE_SEQ_WIDTH, seq)


def note_seq(name):
    """The sequence number in a current-format note name, or None for a legacy name."""
    parts = name[:-3].split("-") if name.endswith(".md") else name.split("-")
    if len(parts) == 2 and len(parts[1]) == NOTE_SEQ_WIDTH and parts[1].isdigit():
        return int(parts[1])
    return None


def note_order(name):
    """Sort pending notes by submission order, legacy timestamp names first."""
    seq = note_seq(name)
    return (1, seq, "") if seq is not None else (0, 0, name)


def pending_notes(inbox):
    return sorted(inbox.glob("note-*.md"), key=lambda item: note_order(item.name))


def consume_notes(rally):
    """Commit every queued note once, then archive its file.

    The note identity is committed with the note, so an interruption between the
    commit and the archive move cannot deliver the same note twice on resume.
    """
    inbox = rally.out / "inbox"
    archive = inbox / "consumed"
    archive.mkdir(parents=True, exist_ok=True)
    consumed = rally.state.setdefault("consumed_notes", [])
    committed = set(consumed)
    for item in pending_notes(inbox):
        identity = item.name[:-3]
        if identity in committed:
            archive_note(item, archive / item.name)
            continue
        try:
            note = item.read_text(encoding="utf-8").strip()
        except OSError:
            break  # Never let a later note overtake an unreadable earlier one.
        if not note:
            # Publication is still pending. Defer this note and everything after it.
            break
        if identity not in committed:
            rally.state.setdefault("owner_notes", []).append(note)
            consumed.append(identity)
            committed.add(identity)
            rally.save("note", summary="Owner note received", note=note, note_id=identity)
        archive_note(item, archive / item.name)
    return list(rally.state.setdefault("owner_notes", []))


def archive_note(item, destination):
    """Keep the owner's own text; never delete an inbox file outright."""
    try:
        if destination.exists():
            item.unlink()
        else:
            os.replace(item, destination)
    except OSError:
        pass


def next_note_seq(inbox, state):
    highest = 0
    for directory in (inbox, inbox / "consumed"):
        for item in directory.glob("note-*.md"):
            seq = note_seq(item.name)
            if seq is not None:
                highest = max(highest, seq)
    for identity in state.get("consumed_notes") or []:
        seq = note_seq(identity)
        if seq is not None:
            highest = max(highest, seq)
    return highest + 1


def append_note(directory, note):
    note = note.strip()
    if not note:
        raise ValueError("note cannot be empty")
    out, state = load_state(directory)
    if state.get("status") != "running":
        raise ValueError(f"rally is {state.get('status')}; notes can only be added while it is running")
    inbox = out / "inbox"
    (inbox / "consumed").mkdir(parents=True, exist_ok=True)
    seq = next_note_seq(inbox, state)
    while True:
        try:
            # Claiming the name itself orders concurrent submissions without a clock.
            os.close(os.open(str(inbox / note_name(seq)), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            seq += 1
    # Publish the text atomically. The engine reads the inbox while the owner
    # queues notes, so the claimed name must hold either nothing (it waits for a
    # later hit) or the whole note, never a half-written one.
    pending = None
    reserved = inbox / note_name(seq)
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=inbox,
                                         prefix="pending-", suffix=".tmp", delete=False) as f:
            pending = pathlib.Path(f.name)
            f.write(note)
        publish(pending, reserved)
    except BaseException:
        # A failed submission must not leave an empty reservation blocking the queue.
        # If publish succeeded before interruption, leave the complete note intact.
        if reserved.exists() and reserved.stat().st_size == 0:
            reserved.unlink()
        raise
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)
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
    rally = Rally.load(out, state)
    rally.state["status"] = "running"
    rally.state["finished_at"] = None
    rally.save("resume", summary=f"Resuming at hit {len(state['hits']) + 1}/{state['iterations']}")
    set_active(out)
    with terminate_as_cancel():
        rally = execute(rally, players, Progress(), cancelled="Rally paused by user")
    if rally.error:
        print(f"Rally stopped after an engine error: {rally.error}", file=sys.stderr)
    return report_result(rally)


def write_outputs(rally):
    s, out = rally.state, rally.out
    lines = []
    if s["hits"]:
        last = s["hits"][-1]
        lines = [last["version"].rstrip(), "", "---", "",
                 f"Rally: {len(s['hits'])}/{s['iterations']} hits between "
                 + " and ".join(p["label"] for p in s["players"]) + "."]
        if s["status"] != "done":
            lines += ["", f"Partial result: the rally ended {s['status']} after "
                      f"{len(s['hits'])} of {s['iterations']} hits. The version above is the"
                      " last completed one, not a converged final version."]
        lines += ["", "Owner brief (authoritative, as given):", "", s["idea"].strip()]
        over = [h for h in s["hits"] if h.get("over_budget")]
        if over:
            lines += ["", "Size limit retries that remained over budget: "
                      + ", ".join(str(h["n"]) for h in over) + "."]
        lines += open_question_report(s)
        conflicts = [c for h in s["hits"] for c in h.get("owner_conflicts", [])]
        if conflicts:
            lines += ["", "Owner requirements agents proposed changing:"]
            lines += [f"- {c.get('item', 'requirement')}: {c.get('reason', 'no reason supplied')}"
                      for c in conflicts]
    else:
        lines = ["# Ping-pong rally", "",
                 "Partial result: no hit completed, so there is no refined version yet.", "",
                 "Owner brief (authoritative, as given):", "", s["idea"].strip()]
    lines += ["", f"Status: {s['status']}."]
    if s.get("error"):
        lines += ["", f"The engine stopped with an error: {s['error']}"]
    if s.get("faults"):
        lines += ["", "Player errors:"]
        lines += [f"- Hit {f['n']}, {f['player']}: {f['error']}" for f in s["faults"]]
    if s.get("owner_notes"):
        lines += ["", "Owner notes carried through the rally:"]
        lines += [f"- {note}" for note in s["owner_notes"]]
    lines += ledger_report(s)
    (out / "final.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def open_question_report(state):
    """Questions the last hit still asks, kept apart from ones it stopped asking.

    The engine never decides that a question is answered: it only reports which
    ones survived to the last completed version, so the host can check the rest
    against the rally and the owner's own notes instead of relisting them all.
    """
    hits = state.get("hits") or []
    if not hits:
        return []
    def asked(hit):
        return [q for q in (str(x).strip() for x in hit["open_questions"]) if q]

    still_open, earlier = [], []
    for question in asked(hits[-1]):
        if question not in still_open:
            still_open.append(question)
    for hit in hits[:-1]:
        for question in asked(hit):
            if question not in still_open and question not in earlier:
                earlier.append(question)
    lines = []
    if still_open:
        lines += ["", "Questions the last hit still leaves open:"]
        lines += [f"- {q}" for q in still_open]
    if earlier:
        lines += ["", "Questions raised earlier that the last hit no longer asks. Check the final"
                  " version, the owner notes and the ledger before relisting them; do not invent"
                  " answers:"]
        lines += [f"- {q}" for q in earlier]
    return lines


def ledger_report(state):
    """Standing decisions, dropped ones with their reasons, and every dispute."""
    ledger = state.get("ledger") or []
    lines = []
    standing = [e for e in ledger if e.get("status") == "standing"]
    dropped = [e for e in ledger if e.get("status") != "standing"]
    if standing:
        lines += ["", "Decisions standing at the end of the rally:"]
        lines += ["- {0} ({1}): {2}".format(
            e["id"], "owner non-negotiable" if e.get("by") == "owner" else e.get("by") or "player",
            e.get("text", "")) for e in standing]
    if dropped:
        lines += ["", "Decisions dropped during the rally:"]
        lines += ["- {0} ({1}): {2} — dropped because: {3}".format(
            e["id"], e.get("by") or "player", e.get("text", ""),
            e.get("reason") or "no reason recorded") for e in dropped]
    if state.get("disputes"):
        lines += ["", "Ledger disputes (requests the engine refused):"]
        lines += ["- Hit {0}, {1} wanted to {2} {3}: {4} (reason given: {5})".format(
            d.get("n"), d.get("player"), d.get("op", "change"), d.get("id") or "an entry",
            d.get("refused", "refused"), d.get("reason") or "none")
            for d in state["disputes"]]
    return lines


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
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        return setup_command(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        return doctor(sys.argv[2:])
    ap = argparse.ArgumentParser(description="Bounce an idea between two LLMs.")
    ap.add_argument("--idea", help="the idea as text")
    ap.add_argument("--idea-file", help="read the idea from a file")
    ap.add_argument("-n", "--iterations", type=int, default=10, help="number of hits (default 10)")
    ap.add_argument("--players", help="two comma-separated specs from cli:claude, cli:codex, cli:cursor")
    ap.add_argument("--out", help="rally directory from `setup` (default ./.ping-pong/<timestamp>-<slug>)")
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
    found = detect_players()
    specs = [s for s in (a.players.split(",") if a.players else auto_pick(found)) if s.strip()]
    if len(specs) != 2:
        print("Need exactly two players; no player CLIs pair was available.", file=sys.stderr)
        print(missing_players_message(found), file=sys.stderr)
        return 2
    try:
        players = [Player(s) for s in specs]
    except ValueError as exc:
        print(f"Invalid player spec: {exc}", file=sys.stderr)
        return 2
    if not preflight_players(players):
        print("Rally not started: player preflight failed. Fix the issue or choose different players.",
              file=sys.stderr)
        return 1

    try:
        out = new_rally_dir(idea, a.out)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    srv = None
    if a.animation and animation_enabled():
        try:
            srv = serve_animation(out)
            print(f"animation: http://127.0.0.1:{srv.server_port}/", flush=True)
        except OSError as exc:
            print(f"Animation unavailable ({exc}); rally continues.", file=sys.stderr)

    print(f"rally: {players[0].label} vs {players[1].label}, {a.iterations} hits", flush=True)
    print(f"dir: {out}", flush=True)
    try:
        with terminate_as_cancel():
            try:
                rally = play(idea.strip(), a.iterations, players, out, Progress())
            except (OSError, ValueError) as exc:
                # The rally never started, so there is no state to finalize.
                print(f"Rally could not start: {exc}", file=sys.stderr)
                return 1
        if rally.error:
            print(f"Rally stopped by an engine error: {rally.error}", file=sys.stderr)
        return report_result(rally)
    finally:
        if srv:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    sys.exit(main())
