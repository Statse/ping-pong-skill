# Players

A player spec is `kind:name[:model]`. Pass two, comma-separated: `--players cli:claude,cli:codex`.
Three agent CLIs are supported. There is no API transport, no adapter registry, and no
arbitrary-command player: an unsupported spec fails before any provider request.

## Agent CLIs (no API key needed if you are logged in)

| Spec | Needs | Notes |
|---|---|---|
| `cli:claude` / `cli:claude:<model>` | `claude` on PATH | Uses `claude -p`; optional model alias |
| `cli:codex` / `cli:codex:<model>` | `codex` on PATH | Uses `codex exec` |
| `cli:cursor` / `cli:cursor:<model>` | `cursor-agent` or `agent` on PATH | Uses `agent -p --mode ask` |

CLIs run in a fresh temp directory so they cannot touch your repo. Model names are passed through
as given; the engine never substitutes or guesses a model, and does not enumerate model catalogs.

## Auto pick

Without `--players` the rally is **Claude against Codex**. If that pair is not installed, the first
two detected supported CLIs are used instead. With fewer than two, the engine reports what it found,
which default CLI is missing, and how to pick a pair — it never substitutes another provider or
invents a model alias.

Two independent sessions of the same CLI are a valid rally, but only as an explicit choice:

```sh
python3 scripts/rally.py --idea "an idea" --players cli:codex,cli:codex
```

API keys in the environment (`ANTHROPIC_API_KEY` and friends) have no effect on detection or
selection.

## Testing

`mock:<name>` returns canned replies after a short delay. Use it to test the rally or the optional
pixel animation without credentials.

## Preflight

Before each rally, ping-pong sends a short format request to both selected players. Each must return
a valid JSON envelope with the expected `version: "pong"`. The rally does not start if either probe
fails. Preflight calls and size repairs are not hits. Check a pair manually:

```sh
python3 scripts/rally.py doctor --players cli:claude,cli:codex
```

Preflight uses the selected CLI, confirming that its login and model access work.
