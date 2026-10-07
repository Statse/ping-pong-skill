# Players

A player spec is `kind:name[:model]`. Pass two, comma-separated: `--players cli:claude,cli:codex`.

## Agent CLIs (no API key needed if you are logged in)

| Spec | Needs | Notes |
|---|---|---|
| `cli:claude` / `cli:claude:opus` | `claude` on PATH | Uses `claude -p`; optional model alias |
| `cli:codex` / `cli:codex:<model>` | `codex` on PATH | Uses `codex exec` |
| `cli:cursor` / `cli:cursor:<model>` | `cursor-agent` or `agent` on PATH | Uses `agent -p --mode ask` |
| `cli:opencode` / `cli:opencode:<provider/model>` | `opencode` on PATH | Uses `opencode run` |
| `cli:copilot` / `cli:copilot:<model>` | `copilot` on PATH | Uses `copilot -s -p` |
| `cli:gemini` / `cli:gemini:<model>` | `gemini` on PATH | Uses `gemini -p` |
| `cli:<any-command>` | the command on PATH | Prompt goes to stdin, answer is read from stdout |

CLIs run in a fresh temp directory so they cannot touch your repo.

## APIs

| Spec | Key env var | Default model env var |
|---|---|---|
| `anthropic:<model>` | `ANTHROPIC_API_KEY` | `PINGPONG_ANTHROPIC_MODEL` |
| `openai:<model>` | `OPENAI_API_KEY` | `PINGPONG_OPENAI_MODEL` |
| `gemini:<model>` | `GEMINI_API_KEY` | `PINGPONG_GEMINI_MODEL` |
| `openrouter:<vendor/model>` | `OPENROUTER_API_KEY` | `PINGPONG_OPENROUTER_MODEL` |

Model names change often; if a default is rejected, set the env var or put the model in the spec.

## Auto pick

Without `--players`, the script detects CLIs first (Claude, Codex, Cursor, OpenCode, Copilot, Gemini), then API keys, and picks two from different vendors. Cursor, OpenCode and Copilot can run several vendors' models, so name the model in the spec if you want a guaranteed cross-vendor rally, e.g. `cli:claude` against `cli:cursor:<a non-Claude model>`. With only Claude available it plays Opus against Sonnet.

## Testing

`mock:<name>` returns canned replies after a short delay. Use it to test the rally or the optional pixel animation.

## Preflight

Before each rally, ping-pong sends a short format request to both selected players. Each must return
a valid JSON envelope with the expected `version: "pong"`. The rally does not start if either probe
fails. Check a pair manually:

```sh
python3 scripts/rally.py doctor --players cli:claude,cli:codex
```

Preflight uses the selected CLI or API provider, confirming that authentication and model access work.
