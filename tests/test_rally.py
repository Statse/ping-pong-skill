"""Credential-free contracts for the engine, CLI, and lifecycle and deliverables."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'ping-pong' / 'scripts' / 'rally.py'
spec = importlib.util.spec_from_file_location('rally', SCRIPT)
rally = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rally)


class ParserTests(unittest.TestCase):
    def test_envelopes(self):
        version = '# Idea\n\n' + 'Quoted "text", backslash \\, ää 🏓.\n' * 800
        payload = json.dumps({'version': version, 'changes': ['Keep it'], 'open_questions': ['Why?']})
        for text in (payload, '```json\n' + payload + '\n```', 'Here you go:\n' + payload):
            with self.subTest(wrapper=text[:12]):
                reply = rally.parse_reply(text)
                self.assertTrue(reply['parsed'])
                self.assertEqual(reply['version'], version)
                self.assertEqual(reply['changes'], ['Keep it'])

    def test_malformed_replies_remain_identifiable(self):
        # Slice #7 will turn these into faults. This slice preserves the v1 contract.
        for text in ('prose', '', '{broken', '}', '{}', '[]', '{"version": ""}'):
            with self.subTest(text=text):
                self.assertFalse(rally.parse_reply(text)['parsed'])


class DriftTests(unittest.TestCase):
    """Fixtures with known retention; the v1 baseline is in docs/evidence/."""

    VERSION = ('# Café idea\n\n'
               'A quiet espresso bar for table tennis players near the station.\n'
               'It opens at six so the morning league can play before work.\n'
               'Short line\n')

    def test_identical_version_keeps_every_line(self):
        measured = rally.drift(self.VERSION, self.VERSION)
        self.assertEqual(measured['lines_kept'], 1.0)
        self.assertEqual(measured['size_ratio'], 1.0)

    def test_full_rewrite_keeps_nothing(self):
        measured = rally.drift(self.VERSION, '# Something else entirely, written from scratch now.\n')
        self.assertEqual(measured['lines_kept'], 0.0)

    def test_one_edited_section_is_partial(self):
        edited = self.VERSION.replace('It opens at six so the morning league can play before work.',
                                      'It opens at five for the morning league, and serves pastries.')
        measured = rally.drift(self.VERSION, edited)
        # Two substantial incoming lines; one survives verbatim. 'Short line' is too short to count.
        self.assertEqual(measured['lines_kept'], 0.5)

    def test_serve_has_no_ratio_and_does_not_divide_by_zero(self):
        for incoming in (None, '', '   \n\n'):
            with self.subTest(incoming=repr(incoming)):
                self.assertEqual(rally.drift(incoming, self.VERSION),
                                 {'lines_kept': None, 'size_ratio': None})

    def test_incoming_without_substantial_lines_still_reports_size(self):
        measured = rally.drift('tiny\nalso tiny\n', self.VERSION)
        self.assertIsNone(measured['lines_kept'])
        self.assertGreater(measured['size_ratio'], 1)

    def test_plain_language_rendering(self):
        self.assertEqual(rally.drift_text({'lines_kept': 0.01, 'size_ratio': 1.68}),
                         'rewrote 99 % of lines, 1.68x the length')
        self.assertEqual(rally.drift_text({'lines_kept': None, 'size_ratio': 2.0}),
                         '2.00x the length')
        self.assertEqual(rally.drift_text({'lines_kept': None, 'size_ratio': None}), '')


class RallyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.active = patch.object(rally, 'ACTIVE', self.directory / 'home' / 'active.json')
        self.active.start()
        self.addCleanup(self.active.stop)
        self.players = [rally.Player('mock:left'), rally.Player('mock:right')]

    def new_rally(self):
        return rally.Rally('An idea ää 🏓', 4, self.players, self.directory)

    def play(self):
        with patch.object(rally.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            return rally.play('An idea ää 🏓', 4, self.players, self.directory,
                              rally.Progress())

    def test_event_cursors_and_finished_default(self):
        game = self.play()
        rally.write_outputs(game)
        after = 0
        types = []
        for expected in range(1, 7):
            event, state, code = rally.wait_for_event(self.directory, after, 0)
            self.assertEqual(code, 0)
            self.assertEqual(event['id'], expected)
            self.assertGreaterEqual(state['event_id'], event['id'])
            types.append(event['type'])
            after = event['id']
        self.assertEqual(types, ['serve', 'hit', 'hit', 'hit', 'hit', 'done'])
        self.assertEqual(rally.wait_for_event(self.directory, after, 0)[2], 2)
        self.assertEqual(rally.wait_for_event(self.directory, timeout=0)[0]['type'], 'done')
        self.assertEqual(len(game.state['hits']), 4)
        self.assertIn('Mock version after hit 4', (self.directory / 'final.md').read_text(encoding='utf-8'))
        self.assertEqual(rally.load_state()[1], game.state)

    def test_every_hit_carries_drift_and_status_renders_it(self):
        game = self.play()
        serve, later = game.state['hits'][0], game.state['hits'][1:]
        for hit in game.state['hits']:
            self.assertIn('lines_kept', hit)
            self.assertIn('size_ratio', hit)
        self.assertIsNone(serve['size_ratio'])
        self.assertTrue(all(hit['size_ratio'] is not None for hit in later))
        self.assertIn('Last hit ', rally.status_text(game.state))
        self.assertIn('x the length', rally.status_text(game.state))
        stored = json.loads((self.directory / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual([hit['size_ratio'] for hit in stored['hits']],
                         [hit['size_ratio'] for hit in game.state['hits']])

    def test_state_published_before_every_event(self):
        original_open = Path.open
        observations = []

        def observe(path, mode='r', *args, **kwargs):
            if path.name == 'events.jsonl' and mode == 'a':
                state = json.loads((self.directory / 'state.json').read_text(encoding='utf-8'))
                observations.append(state)
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, 'open', observe):
            self.play()
        self.assertEqual([s['event_id'] for s in observations], list(range(1, 7)))
        self.assertEqual([len(s['hits']) for s in observations], [0, 1, 2, 3, 4, 4])
        self.assertEqual(observations[-1]['status'], 'done')

    def test_timeout_prints_status(self):
        game = self.new_rally()
        game.state['current'] = {'n': 1, 'side': 0, 'started_at': rally._now_ms()}
        game.save()
        output = io.StringIO()
        started = time.monotonic()
        with contextlib.redirect_stdout(output):
            code = rally.watch_command('wait', ['--dir', str(self.directory), '--after', '1', '--timeout', '1'])
        self.assertEqual(code, 2)
        self.assertGreaterEqual(time.monotonic() - started, 1)
        self.assertIn('Rally running: 0/4 turns completed.', output.getvalue())
        self.assertIn('timeout:', output.getvalue())

    def test_partial_event_is_not_delivered(self):
        self.new_rally()
        with (self.directory / 'events.jsonl').open('a', encoding='utf-8') as f:
            f.write('{"id": 2')
        self.assertEqual(rally.wait_for_event(self.directory, 1, 0)[2], 2)

    def test_faults_and_terminal_error(self):
        with patch.object(rally.Player, 'call', side_effect=RuntimeError('unavailable')):
            game = self.play()
        self.assertEqual(game.state['status'], 'error')
        self.assertIsNotNone(game.state['finished_at'])
        event, _, code = rally.wait_for_event(self.directory, timeout=0)
        self.assertEqual((event['type'], code), ('error', 1))
        entries = [json.loads(line) for line in (self.directory / 'events.jsonl').read_text().splitlines()]
        self.assertEqual([e['type'] for e in entries], ['serve', 'fault', 'fault', 'error'])
        self.assertEqual(rally.wait_for_event(self.directory, 0, 0)[2], 0)

    def test_ten_turn_baseline_with_same_cli_configuration(self):
        players = [rally.Player('cli:codex'), rally.Player('cli:codex')]
        reply = json.dumps({'version': 'Refined idea', 'changes': ['Improved']})
        with patch.object(rally.Player, 'call', return_value=reply) as call, \
                contextlib.redirect_stdout(io.StringIO()):
            game = rally.play('Tinder for houses', 10, players, self.directory, rally.Progress())
        self.assertEqual(call.call_count, 10)
        self.assertEqual([hit['side'] for hit in game.state['hits']], [0, 1] * 5)
        self.assertEqual(game.state['status'], 'done')
        self.assertEqual([p['spec'] for p in game.state['players']], ['cli:codex', 'cli:codex'])

    def test_cancel_records_stopped_and_keeps_completed_turns(self):
        replies = [json.dumps({'version': 'Keep this work'}), KeyboardInterrupt()]
        with patch.object(rally.Player, 'call', side_effect=replies):
            game = self.play()
        self.assertEqual(game.state['status'], 'stopped')
        self.assertEqual(len(game.state['hits']), 1)
        rally.write_outputs(game)
        self.assertIn('Keep this work', (self.directory / 'final.md').read_text())
        self.assertEqual(rally.wait_for_event(self.directory, timeout=0)[0]['type'], 'stopped')

    def test_startup_cancellation_publishes_terminal_state(self):
        original = rally.Rally.save

        def interrupt_after_serve(game, event=None, **details):
            original(game, event, **details)
            if event == 'serve':
                raise KeyboardInterrupt()

        with patch.object(rally.Rally, 'save', interrupt_after_serve):
            game = self.play()
        self.assertEqual(game.state['status'], 'stopped')
        self.assertEqual(rally.load_state(self.directory)[1]['status'], 'stopped')
        self.assertEqual(rally.wait_for_event(self.directory, timeout=0)[0]['type'], 'stopped')

    def test_existing_rally_is_not_overwritten(self):
        game = self.play()
        with self.assertRaises(FileExistsError):
            self.new_rally()
        self.assertEqual(rally.load_state(self.directory)[1], game.state)

    def test_missing_directory_is_clear_error(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = rally.watch_command('wait', ['--dir', str(self.directory / 'missing')])
        self.assertEqual(code, 1)
        self.assertIn('Cannot read rally:', stderr.getvalue())
        self.assertNotIn('Traceback', stderr.getvalue())



class ProcessTests(unittest.TestCase):
    def test_doctor_without_clis(self):
        with tempfile.TemporaryDirectory() as empty:
            result = subprocess.run([sys.executable, str(SCRIPT), 'doctor'],
                                    env={**os.environ, 'PATH': empty}, capture_output=True,
                                    text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn('PLAYERS.md', result.stderr)
        self.assertIn('No player CLIs', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_cli_timeout_kills_process_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'should-not-exist'
            descendant = 'import time,pathlib; time.sleep(1); pathlib.Path({!r}).touch()'.format(str(marker))
            parent = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{!r}]); time.sleep(30)'.format(descendant)
            with self.assertRaises(subprocess.TimeoutExpired):
                rally.run_cli([sys.executable, '-c', parent], None, directory, 0.4)
            time.sleep(1.1)
            self.assertFalse(marker.exists(), 'timed-out CLI left a running descendant')

    def test_real_mock_rally_and_wait_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            # Isolate the active pointer from the user's actual rally.
            environment = {**os.environ, 'HOME': directory, 'USERPROFILE': directory, 'PYTHONUTF8': '1'}
            out = Path(directory) / 'run'
            process = subprocess.Popen(
                [sys.executable, str(SCRIPT), '--idea', 'A café for 🏓', '-n', '4',
                 '--players', 'mock:left,mock:right', '--no-animation', '--out', str(out)],
                env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8')
            try:
                deadline = time.monotonic() + 10
                while not (out / 'state.json').exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        self.fail('mock rally failed to start')
                    time.sleep(0.05)
                cursor = 0
                kinds = []
                for _ in range(6):
                    response = subprocess.run(
                        [sys.executable, str(SCRIPT), 'wait', '--dir', str(out),
                         '--after', str(cursor), '--timeout', '10'],
                        env=environment, capture_output=True, text=True, encoding='utf-8', timeout=15)
                    self.assertEqual(response.returncode, 0, response.stderr + response.stdout)
                    match = re.search(r'^event (\d+): (\w+)', response.stdout, re.M)
                    self.assertIsNotNone(match, response.stdout)
                    self.assertEqual(int(match[1]), cursor + 1)
                    cursor = int(match[1])
                    kinds.append(match[2])
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(kinds, ['serve', 'hit', 'hit', 'hit', 'hit', 'done'])
                self.assertIn('status: done', stdout)
                self.assertFalse((out / 'replay.html').exists())
                final = (out / 'final.md').read_text(encoding='utf-8')
                self.assertIn('Mock version after hit 4', final)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate()


if __name__ == '__main__':
    unittest.main()
