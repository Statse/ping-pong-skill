# Optional pixel animation verification — 2026-10-06

Local work for issue #16. No host-native adapter has been installed or certified.

- Python 3.9.6: 21 unittest checks passed, including a real four-turn mock process, ten alternating
  turns using the same CLI configuration with stubbed replies, cancellation (including startup),
  timeout child cleanup, event cursor ordering, preferences and restricted local adapter routes.
- `node --check` passed for `widget.js` and `adapter.js`.
- Collaborative browser: visually inspected two pixel paddles and a moving ball; computed transforms
  changed across samples. The component has no score, transcript or turn meter.
- `done`, `error`, `stopped`, `idle`, and `disconnected` each hid the illustration and left zero CSS
  animations. The same checks passed with animation disabled while lifecycle remained `running`.
- Clicking Animation saved `false` to an isolated temporary settings file; after reloading the
  widget remained disabled, hidden and without animations. Re-enabling restored the loop.
- Updating the served lifecycle to `done` stopped the widget through its polling adapter.
- Terminating the preview server caused `disconnected`, hidden illustration, and zero animations.
- Reduced-motion behavior is implemented via a media query; OS-level emulation was not available in
  the collaborative browser, so this remains code-inspected rather than independently exercised.
- `git diff --check` passed. Skill is 42 lines and local links resolve. The bundled skill validator
  could not run because PyYAML is absent; no package was installed. Basic frontmatter/structure and
  resource checks were performed directly using Python's standard library.

The six-cell GitHub Actions matrix remains unrun because these changes are uncommitted/unpushed.
All display testing used temporary settings; the owner's animation preference was not changed.
