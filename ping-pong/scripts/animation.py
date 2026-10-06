"""Optional local adapter for the host-neutral pixel widget. Python stdlib only."""
import argparse
import http.server
import json
import os
from pathlib import Path
import tempfile
import threading

SETTINGS = Path.home() / '.ping-pong' / 'settings.json'
ASSETS = Path(__file__).resolve().parents[1] / 'assets'


def read_settings():
    if not SETTINGS.exists():
        return {}
    value = json.loads(SETTINGS.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('animation settings must be a JSON object')
    return value


def animation_enabled():
    try:
        return read_settings().get('animation', True) is True
    except (OSError, ValueError):
        return False  # A broken preference must not force motion on.


def set_animation(enabled):
    settings = read_settings()
    settings['animation'] = enabled
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=SETTINGS.parent,
                                     prefix='settings-', delete=False) as stream:
        json.dump(settings, stream, indent=2)
        stream.write('\n')
    try:
        os.replace(stream.name, SETTINGS)
    finally:
        Path(stream.name).unlink(missing_ok=True)


def animation_command(argv):
    parser = argparse.ArgumentParser(prog='rally.py animation')
    parser.add_argument('setting', choices=['on', 'off', 'status'])
    args = parser.parse_args(argv)
    try:
        if args.setting != 'status':
            set_animation(args.setting == 'on')
        print('Animation ' + ('on' if animation_enabled() else 'off'))
        return 0
    except (OSError, ValueError) as exc:
        print(f'Cannot update animation preference: {exc}')
        return 1


def serve_animation(out):
    """Only widget assets and lifecycle are exposed; idea/transcript stay private."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, payload, mime='application/json', status=200):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/status':
                try:
                    state = json.loads((out / 'state.json').read_text(encoding='utf-8'))
                    status = state['status']
                except (OSError, ValueError, KeyError):
                    status = 'idle'
                self.send({'status': status, 'enabled': animation_enabled()})
            elif self.path in ('/', '/widget.js', '/adapter.js'):
                name = 'widget.html' if self.path == '/' else self.path[1:]
                mime = 'text/html; charset=utf-8' if self.path == '/' else 'text/javascript; charset=utf-8'
                self.send((ASSETS / name).read_bytes(), mime)
            else:
                self.send_error(404)

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if (self.path != '/enabled' or self.headers.get('Origin') != origin
                    or self.headers.get('Content-Type') != 'application/json'):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length < 100:
                    raise ValueError('invalid preference length')
                value = json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(value, dict) or type(value.get('enabled')) is not bool:
                    raise ValueError('enabled must be boolean')
                set_animation(value['enabled'])
                self.send({'enabled': animation_enabled()})
            except (OSError, ValueError) as exc:
                self.send({'error': str(exc)}, status=400)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
