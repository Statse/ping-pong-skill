# Ping-pong animation host support

Investigated 2026-10-06 against official documentation and first-party source. This is a capability assessment, not a claim that adapters have been installed or tested. Features and versions can change.

## Scope and conclusion

The requested visual is two pixel paddles exchanging a ball for the duration of a rally, with no score or turn-by-turn synchronization. It must be independently disableable without disabling the idea-refinement engine.

**This is not limited to Copilot.** Documented integration surfaces exist in VS Code/Copilot and Cursor through MCP Apps, and in Claude Code CLI/Desktop through mods. Codex also has native custom-pet facilities, with important lifecycle and terminal constraints. There is no single documented extension surface that places the same animation above every host's input.

Confidence below concerns the documented surface. Every proposed ping-pong adapter still needs an end-to-end test, including its connection to the local rally lifecycle.

## Support matrix

| Host | Documented display route | Fit and limitations | Confidence |
| --- | --- | --- | --- |
| Copilot in VS Code | MCP App rendered inline in chat; separate extension webview | Real chat content, but inline only: not a persistent pet above the input. A webview is a separate editor/sidebar view. [MCP developer guide](https://code.visualstudio.com/api/extension-guides/ai/mcp), [Webview API](https://code.visualstudio.com/api/extension-guides/webview) | High |
| VS Code built-in `/vscode-pet` | Experimental built-in pet above chat input | Its reactions are documented; a public custom sprite registration or exact rally-state API was not found in the reviewed pet/API docs. Do not promise replacing this pet. [Pet reference](https://code.visualstudio.com/docs/agents/reference/chat-pet) | High for built-in behavior; custom replacement unverified |
| Cursor editor | MCP Apps interactive UI in chat | Official docs explicitly confirm support and ordinary MCP-response fallback. Suitable shared HTML renderer candidate; pinned-input placement and lifecycle persistence need verification. [Cursor MCP integrations](https://prod.cursor.com/help/customization/mcp) | High |
| Cursor editor, separate view | Compatible VS Code extension or built-in browser pane | Alternative companion placement, not injection into Cursor's chat internals. Exact extension compatibility must be tested. [Extensions](https://prod.cursor.com/help/customization/extensions), [Browser](https://prod.cursor.com/docs/agent/tools/browser), [Webview API](https://code.visualstudio.com/api/extension-guides/webview) | Medium for a new extension; browser documented |
| Cursor CLI | Hooks/process integration; companion terminal or browser renderer | Reviewed CLI docs expose text/JSON/stream-JSON output, and hooks operate through scripts. No public arbitrary inline animation surface or custom statusline renderer was established by these docs. Companion rendering is an engineering fallback, not native chat support. [CLI parameters](https://cursor.com/docs/cli/reference/parameters), [Hooks](https://cursor.com/docs/hooks) | High for documented interfaces; native animation unverified |
| Claude Code CLI | Mod pane or band above prompt | Direct native UI extension route. Terminal mods require Claude Code 2.1.287+. Raster cells and redraw APIs make this a strong candidate. [Mods overview](https://code.claude.com/docs/en/plugins/mods/overview), [Mods reference](https://code.claude.com/docs/en/plugins/mods/reference) | High |
| Claude Desktop, Code tab | Mod pane or band above prompt | Supported from bundled Claude Code 2.1.286+, except WSL sessions. Desktop elements differ from terminal elements: use a Desktop-compatible renderer. [Mods overview](https://code.claude.com/docs/en/plugins/mods/overview), [Elements](https://code.claude.com/docs/en/plugins/mods/reference#elements) | High |
| Claude Code VS Code extension | Separate VS Code companion webview | Mod hooks run but their UI explicitly does not render in this chat panel. Running Claude in the integrated terminal is a different surface and supports mod UI. [Where mods run](https://code.claude.com/docs/en/plugins/mods/overview#where-mods-run), [Webview API](https://code.visualstudio.com/api/extension-guides/webview) | High |
| Claude Code headless / SDK / cloud | Lifecycle integration, externally rendered companion | Mods can run where plugins load, but documented mod UI does not appear in headless/SDK/cloud sessions. Remote Control leaves mod graphics in the originating terminal. [Where mods run](https://code.claude.com/docs/en/plugins/mods/overview#where-mods-run) | High |
| Claude normal chat / Cowork | MCP Apps | Interactive connectors are documented on web, mobile, desktop and Cowork. This is not evidence that the Claude Code VS Code panel supports MCP Apps. A connector also needs a way to reach the rally process. [Anthropic announcement](https://claude.com/blog/interactive-tools-in-claude) | High for those named surfaces |
| Copilot CLI | Hooks, experimental extensions, custom statusline command | Good lifecycle/companion integration options. First-party changelog confirms `statusLine.command`, but reviewed sources do not establish a smooth pixel-animation cadence or inline HTML surface. [Hooks](https://docs.github.com/en/copilot/reference/hooks-reference), [CLI extensions](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-cli-extensions), [Changelog](https://github.com/github/copilot-cli/blob/main/changelog.md) | High for interfaces; animation unverified |
| GitHub Copilot app | Canvas extension in right side panel | Custom interactive surface with shared state. Separate from Copilot VS Code and CLI; do not infer that CLI can display the same panel. [Canvas extensions](https://docs.github.com/en/copilot/how-tos/github-copilot-app/working-with-canvas-extensions) | High |
| Codex CLI | Native pet picker, compatible installed custom pets | `/pets` or `/pet`; `/pets off` disables it. Requires iTerm2 3.6+ or Kitty/Sixel support; unavailable in tmux/Zellij. Native session states are not guaranteed to match a single rally. [OpenAI pets documentation](https://learn.chatgpt.com/docs/pets) | High for native capability; rally adapter untested |
| Codex desktop / ChatGPT desktop | Custom floating pet | Native pet creation provides a sprite route. It follows host activity, not a documented rally-specific start/stop contract. [OpenAI pets documentation](https://learn.chatgpt.com/docs/pets) | High for pets; exact lifecycle unverified |
| Codex IDE extension | Separate editor companion candidate | OpenAI explicitly says this surface has no pet picker/overlay. ChatGPT UI plugin docs describe ChatGPT, not a general Codex UI API. [Pets](https://learn.chatgpt.com/docs/pets), [ChatGPT UI plugins](https://developers.openai.com/plugins/build/chatgpt-ui) | High for stated limitation |
| T3 Code | Companion preview/browser candidate | This task's runtime describes a collaborative preview surface. The reviewed [public repository](https://github.com/pingdotgg/t3code) did not establish a public plugin API for arbitrary chat-embedded animation. Verify preview availability in the target build; do not call it a native chat pet. | Medium for companion route; embedding unverified |

## What the promising routes actually allow

### Shared MCP App for VS Code and Cursor

VS Code documents a tool plus `ui://` HTML resource in a sandboxed iframe. Its SDK can call server tools, receive tool results and handle cancellation/teardown. Only inline display is supported there. This makes a small self-animating view plausible; exact attachment during a long-running rally must be tested. [VS Code MCP developer guide](https://code.visualstudio.com/api/extension-guides/ai/mcp)

Proposed adapter: show the app and return promptly with a run ID; let the engine continue separately; have UI read that run's state through an app-accessible server tool. Do not hold the only tool result until the rally ends, or rely on model-generated frame updates. Check each host's negotiated UI capability, permissions, background lifecycle and teardown behavior. This is a design inference, not a verified implementation.

### Claude mods: closest documented match to a pet beside the prompt

The `AbovePrompt` band and `Pane` sites are public render locations. Terminal `Raster`/`Image` and Desktop `Svg` have different availability. Redraw invalidation is capped at 10 Hz, or 30 Hz in the terminal for the visible pane, expanded band and prompt hint. This bounds the animation design. [Mods reference](https://code.claude.com/docs/en/plugins/mods/reference)

`$.clock.every` permits work between turns without starting a model turn. Raster updates can use `$.ui.blit` to repaint an existing element. The shared band must preserve other mods' output. Persistent preferences can use the documented store, with its cleanup semantics considered. [Mods API](https://code.claude.com/docs/en/plugins/mods/api), [Drawing and persistence](https://code.claude.com/docs/en/plugins/mods/interface)

A legacy Claude statusline is a weaker fallback: event-driven execution is debounced at 300 ms, not a 300 ms animation clock; optional timed refresh has a one-second minimum. It supports multiline colored text but is unsuitable for the intended smooth pixel loop. [Statusline documentation](https://code.claude.com/docs/en/statusline)

### CLI companions

A separately owned terminal pane can draw character/block frames without fighting the agent TUI. A local browser companion can show the same pixel renderer as an MCP App. These are portable architecture options, not evidence of native embedding. Headless/CI should emit no animation; disable must avoid launching either renderer. Hooks alone are lifecycle signals, not display surfaces. Copilot's experimental long-lived JavaScript extensions can observe tool events, which is useful for a companion bridge. [Copilot extension tutorial](https://docs.github.com/en/copilot/tutorials/create-an-extension)

## Recommended next steps

1. Keep the engine host-neutral and authoritative for `running`, `done`, `error`, and `stopped`, identified by a run ID. A whole host turn or session is not necessarily the rally.
2. Preserve a persistent animation preference and a per-run override. Disabling animation must stop timers/renderers immediately and leave agents working. Respect reduced motion and pause hidden views.
3. Prototype an MCP App adapter against both VS Code and Cursor; verify it appears before completion and receives terminal state while the engine is busy.
4. Prototype a Claude mod adapter for terminal and Desktop separately, using the same animation geometry and the documented per-surface elements.
5. Treat native Codex pets as a separate integration spike: confirm custom asset installation and whether exact rally lifecycle control is possible without disrupting the user's selected pet.
6. Retain an explicit companion option for unsupported hosts and a no-animation fallback everywhere. Never inject frames into captured tool stdout or JSON protocols.

Acceptance checks for every adapter: launch before first agent work; loop through waits; stop on success/error/cancel; no scores; no extra model calls per frame; disable persists; concurrent runs do not stop one another; reconnect does not revive a finished run; unsupported UI leaves the baseline command working.
