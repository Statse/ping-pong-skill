#!/usr/bin/env python3
"""Install, check or remove the rally pet in an agent's own UI.

  setup_pet.py --host claude|cursor|opencode|codex|copilot [--status | --uninstall]

claude    statusline (wraps any existing statusline, sets refreshInterval 1)
cursor    statusline in cli-config.json (replaces Cursor's native footer while installed)
opencode  plugin that shows a toast on every serve and at the end
codex, copilot: no custom UI hook exists; the rally uses the browser court and chat frames.
A backup of every edited file goes to ~/.ping-pong/backups/.
"""
import argparse
import json
import os
import pathlib
import shlex
import shutil
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
HOME = pathlib.Path.home()
BACKUPS = HOME / ".ping-pong" / "backups"
PET = HERE / "pet.py"
MARK = "pet.py"


def settings_path(host):
    if host == "claude":
        return HOME / ".claude" / "settings.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and (pathlib.Path(xdg) / "cursor" / "cli-config.json").exists():
        return pathlib.Path(xdg) / "cursor" / "cli-config.json"
    return HOME / ".cursor" / "cli-config.json"


def opencode_plugin():
    base = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
    return base / "opencode" / "plugins" / "ping-pong-pet.js"


def read_json(p):
    return json.loads(p.read_text()) if p.exists() and p.read_text().strip() else {}


def backup(p, host):
    BACKUPS.mkdir(parents=True, exist_ok=True)
    meta = BACKUPS / f"{host}.json"
    if not meta.exists():  # keep the first, pre-pet state
        meta.write_text(json.dumps({"path": str(p), "existed": p.exists(),
                                    "statusLine": read_json(p).get("statusLine") if p.exists() else None}))
    if p.exists():
        shutil.copy(p, BACKUPS / f"{host}-{time.strftime('%Y%m%d-%H%M%S')}.json")


def statusline(host, action):
    p = settings_path(host)
    cfg = read_json(p)
    current = cfg.get("statusLine") or {}
    installed = MARK in str(current.get("command", ""))
    if action == "status":
        return f"{host}: pet {'installed' if installed else 'not installed'} ({p})"
    if action == "install":
        if installed:
            return f"{host}: pet already installed ({p})"
        backup(p, host)
        cmd = f"{shlex.quote(sys.executable)} {shlex.quote(str(PET))}"
        if current.get("command"):
            cmd += f" --wrap {shlex.quote(current['command'])}"
        new = {**current, "type": "command", "command": cmd}
        if host == "claude":
            new["refreshInterval"] = 1
        cfg["statusLine"] = new
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cfg, indent=2) + "\n")
        note = (" Restart Claude Code. Needs v2.1.97+ for the moving ball." if host == "claude" else
                " Restart the Cursor CLI. While installed, the pet line replaces Cursor's native footer.")
        return f"{host}: pet installed in {p}.{note}"
    # uninstall
    meta = BACKUPS / f"{host}.json"
    if not installed:
        return f"{host}: pet not installed"
    original = json.loads(meta.read_text()).get("statusLine") if meta.exists() else None
    if original:
        cfg["statusLine"] = original
    else:
        cfg.pop("statusLine", None)
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    meta.unlink(missing_ok=True)
    return f"{host}: pet removed, previous statusline restored ({p})"


def opencode(action):
    dst = opencode_plugin()
    if action == "status":
        return f"opencode: pet {'installed' if dst.exists() else 'not installed'} ({dst})"
    if action == "install":
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(HERE / "opencode-pet.js", dst)
        return f"opencode: pet plugin installed at {dst}. Restart OpenCode."
    dst.unlink(missing_ok=True)
    return "opencode: pet plugin removed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, choices=["claude", "cursor", "opencode", "codex", "copilot"])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--status", action="store_true")
    g.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()
    action = "status" if a.status else "uninstall" if a.uninstall else "install"
    if a.host in ("codex", "copilot"):
        print(f"{a.host}: no custom UI hook available, so there is no pet. "
              "Use the browser court and the chat frames (pet.py --frame).")
        return 0
    print(opencode(action) if a.host == "opencode" else statusline(a.host, action))
    return 0


if __name__ == "__main__":
    sys.exit(main())
