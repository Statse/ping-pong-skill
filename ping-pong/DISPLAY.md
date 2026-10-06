# Showing the rally

Three layers. The court and the chat frames work in every host; the pet only where the host lets an outside script draw in its UI.

1. **Court**: `rally.py` serves a live page with two paddles and opens it in the browser. Works in terminals, desktop apps and IDEs alike. If the browser does not open by itself (remote machine, sandbox), give the user the printed URL; `replay.html` in the rally dir works offline afterwards.
2. **Chat frames**: each time you poll, run `python3 scripts/pet.py --frame` and paste its output in a code block. Works everywhere, including GUI versions.
3. **Pet**: a small court that lives in the agent's own UI.

| Host | Pet | Install |
|---|---|---|
| Claude Code, terminal | Statusline court; the ball moves every second | `setup_pet.py --host claude` |
| Cursor CLI | Statusline court; redraws when the CLI refreshes its footer, and replaces the native footer while installed | `setup_pet.py --host cursor`, run from a plain terminal with no Cursor CLI session open (a running session overwrites the file on exit) |
| OpenCode TUI | A toast each time the ball is served, and one at the end | `setup_pet.py --host opencode` |
| Codex CLI | None: its status line only takes built-in items | court + frames |
| Copilot CLI | None | court + frames |
| GUI versions: Claude desktop and IDE extension, Cursor editor, Codex app and IDE extension, OpenCode desktop | None: statuslines and TUI plugins are terminal features | court + frames |

Every install backs up the edited file to `~/.ping-pong/backups/`, keeps any existing statusline (the pet line is added under it), and is undone with `--uninstall`. The pet is silent when no rally is running and disappears two minutes after one ends. Restart the host after installing.
