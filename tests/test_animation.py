import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

SCRIPTS = Path(__file__).resolve().parents[1] / 'ping-pong' / 'scripts'
spec = importlib.util.spec_from_file_location('animation', SCRIPTS / 'animation.py')
animation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(animation)


class AnimationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.settings = self.out / 'config' / 'settings.json'
        patcher = patch.object(animation, 'SETTINGS', self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_persistent_disable_preserves_other_settings(self):
        self.settings.parent.mkdir()
        self.settings.write_text('{"other":42}')
        self.assertTrue(animation.animation_enabled())
        animation.set_animation(False)
        self.assertFalse(animation.animation_enabled())
        self.assertEqual(json.loads(self.settings.read_text()), {'animation': False, 'other': 42})
        animation.set_animation(True)
        self.assertTrue(animation.animation_enabled())

    def test_invalid_settings_do_not_force_animation(self):
        self.settings.parent.mkdir()
        self.settings.write_text('broken')
        self.assertFalse(animation.animation_enabled())
        with self.assertRaises(ValueError):
            animation.set_animation(True)
        self.assertEqual(self.settings.read_text(), 'broken')

    def test_widget_adapter_only_exposes_lifecycle_and_preferences(self):
        server = animation.serve_animation(self.out)
        url = 'http://127.0.0.1:{}'.format(server.server_port)
        try:
            self.assertEqual(server.server_address[0], '127.0.0.1')
            for path in ('/', '/widget.js', '/adapter.js'):
                with urllib.request.urlopen(url + path) as response:
                    self.assertEqual(response.status, 200)
            for status in ('running', 'done', 'error', 'stopped'):
                (self.out / 'state.json').write_text(json.dumps({'status': status, 'idea': 'private idea'}))
                with urllib.request.urlopen(url + '/status') as response:
                    self.assertEqual(json.load(response), {'status': status, 'enabled': True})
            for path in ('/state.json', '/final.md', '/../../settings.json'):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(url + path)
                self.assertEqual(caught.exception.code, 404)
                caught.exception.close()
            for origin, expected in (('https://example.com', 403), (url, 200)):
                request = urllib.request.Request(url + '/enabled', data=b'{"enabled":false}',
                    headers={'Content-Type': 'application/json', 'Origin': origin}, method='POST')
                if expected == 403:
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(request)
                    self.assertEqual(caught.exception.code, 403)
                    caught.exception.close()
                else:
                    with urllib.request.urlopen(request) as response:
                        self.assertEqual(json.load(response), {'enabled': False})
            self.assertFalse(animation.animation_enabled())
            self.assertEqual(json.loads((self.out / 'state.json').read_text())['status'], 'stopped')
        finally:
            server.shutdown()
            server.server_close()

    def test_per_run_off_never_starts_widget(self):
        spec = importlib.util.spec_from_file_location('rally', SCRIPTS / 'rally.py')
        rally = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rally)
        out = self.out / 'run'
        argv = ['rally.py', '--idea', 'test', '-n', '1', '--players', 'mock:left,mock:right',
                '--out', str(out), '--no-animation']
        with patch.dict(sys.modules, {'animation': animation}), patch.object(sys, 'argv', argv), \
                patch.object(rally, 'ACTIVE', self.out / 'active.json'), \
                patch.object(rally.time, 'sleep'), patch.object(animation, 'serve_animation') as serve:
            self.assertEqual(rally.main(), 0)
            serve.assert_not_called()
        self.assertTrue((out / 'final.md').exists())

    def test_persistent_off_beats_embed_request(self):
        spec = importlib.util.spec_from_file_location('rally', SCRIPTS / 'rally.py')
        rally = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rally)
        animation.set_animation(False)
        argv = ['rally.py', '--idea', 'test', '-n', '1', '--players', 'mock:left,mock:right',
                '--out', str(self.out / 'run'), '--animation']
        with patch.dict(sys.modules, {'animation': animation}), patch.object(sys, 'argv', argv), \
                patch.object(rally, 'ACTIVE', self.out / 'active.json'), \
                patch.object(rally.time, 'sleep'), patch.object(animation, 'serve_animation') as serve:
            self.assertEqual(rally.main(), 0)
            serve.assert_not_called()


if __name__ == '__main__':
    unittest.main()
