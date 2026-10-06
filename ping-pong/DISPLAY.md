# Optional pixel animation

The display is a small loop: two pixel table-tennis paddles exchange one ball while a rally runs.
It has no scores or turn tracking. Completion, error, cancellation, or engine disconnection stops
it. Reduced-motion settings show a still illustration. The rally works with the display disabled.

## User controls

- Disable future animations: `python3 scripts/rally.py animation off`.
- Enable them again: `python3 scripts/rally.py animation on`.
- Check the preference: `python3 scripts/rally.py animation status`.
- Disable for one rally: add `--no-animation`.
- In an embedded widget, uncheck **Animation** to stop it immediately and save the preference.

The persistent preference is `animation` in `~/.ping-pong/settings.json`. Changing it does not
interrupt players. A persistent off preference takes precedence over an embedding request.

## Host-neutral implementation

`assets/widget.js` defines `<ping-pong-animation>`, a standalone web component with scoped styles.
An adapter sets its `status` property to `running`, `done`, `error`, `stopped`, `idle`, or
`disconnected`, and its `enabled` property to a boolean. Only `running` animates. The component
emits `animation-preference` with `{enabled}` when its checkbox changes; the host persists that
preference. Removing the component stops its animation. The host must report disconnection.

The optional local adapter is runnable now:

```sh
python3 scripts/rally.py --idea "Tinder for houses" -n 10 --players cli:claude,cli:codex --animation
```

This prints an `animation: http://127.0.0.1:<port>/` URL for a host that can embed a local page.
It never launches a browser. Only lifecycle and the display preference are exposed through the
adapter; the idea and player responses are not served. Unchecking the widget saves the persistent
setting. Connection loss stops movement within the request timeout (two seconds plus polling).

Without `--animation`, no display server is created. When a host has no compatible adapter, run the
rally without a display. Do not paste a looping image that cannot stop when the rally ends.

Native chat integration requires a host adapter; installing this skill alone does not provide it.
See the repository's [host support research](../docs/host-animation-support.md) for available APIs
and limits. The standalone skill does not need that research file to run.

## Monitoring the engine

`rally.py wait --dir D --after 0 --timeout 60` returns one event; use its printed event ID as the
next `--after` cursor. Exit codes: 0 event, 2 timeout, 1 error. No cursor on a finished rally reports
its terminal event immediately. `rally.py status --dir D` prints a plain status line. These are
engine monitoring commands, not visual animations.
