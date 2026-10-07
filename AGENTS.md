# Working in this repository

Read `HANDOVER.md` before changing implementation. `SPEC-v2.md` is the current scope;
older GitHub issue text may conflict with newer owner decisions recorded there.

- Keep the engine standard-library-only and Python 3.9-compatible.
- Keep `ping-pong/SKILL.md` under 100 lines.
- Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` for engine changes.
- Use credential-free mocks by default. Live rallies send provider requests.
- Give each active agent a separate branch and worktree. Assign one owner to shared
  engine files, especially `ping-pong/scripts/rally.py`; integrate tested commits in order.
- Never drop or apply a recovery stash wholesale without comparing it with current work.
- Update the handover when implemented behavior or scope changes.
