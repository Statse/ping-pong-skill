<img src="assets/icon.svg" width="64" height="64" alt="">

# ping-pong

`/ping-pong 10 I have a business idea that is Tinder but for houses`

Two configurable agent CLI sessions alternate ten turns refining the idea. The host agent turns
the last version into a plan, build prompt, or spec. Both sessions may use the same CLI.

The optional display is two pixel paddles hitting a ball while work runs. Disable it at any time;
the agents keep working. The host-neutral widget is implemented; native placement needs a host
adapter. See [display controls](ping-pong/DISPLAY.md) and [host support](docs/host-animation-support.md).

Copy `ping-pong/` into your host's skills directory. Python 3.9+; engine uses only the standard library.
For a credential-free check:

```sh
python3 ping-pong/scripts/rally.py --idea "test" -n 4 --players mock:left,mock:right --no-animation
python3 -m unittest discover -s tests -v
```

Current display task: [#16](https://github.com/Statse/ping-pong-skill/issues/16).
Created in [T3 Code](https://t3.codes).
