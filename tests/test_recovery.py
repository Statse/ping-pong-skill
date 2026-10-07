"""Contracts for the engine features recovered from overlapping agent work."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_rally import rally, SCRIPT


def reply(version='A concise idea'):
    return json.dumps({'version': version, 'critique': 'ok', 'changes': [],
                       'open_questions': [], 'owner_conflicts': []})


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.players = [rally.Player('mock:left'), rally.Player('mock:right')]
        for replacement in (patch.object(rally, 'ACTIVE', self.directory / 'active.json'),
                            patch.object(sys, 'path', [str(SCRIPT.parent)] + sys.path),
                            patch.object(rally.time, 'sleep'),
                            contextlib.redirect_stdout(io.StringIO())):
            replacement.__enter__()
            self.addCleanup(replacement.__exit__, None, None, None)

    def play(self, total=4):
        return rally.play('An idea that preserves the owner requirements', total,
                          self.players, self.directory, rally.Progress())

    def test_budget_and_remaining_count_reach_every_player_prompt(self):
        with patch.object(rally.Player, 'call', return_value=reply('x' * 80)) as call:
            game = self.play(10)
        self.assertEqual(call.call_count, 10)
        self.assertEqual([hit['phase'] for hit in game.state['hits']],
                         ['open'] * 3 + ['deepen'] * 4 + ['close'] * 3)
        for n, invocation in enumerate(call.call_args_list, 1):
            system, _ = invocation.args
            hit = game.state['hits'][n - 1]
            self.assertIn(f'{10 - n} iterations remain', system)
            self.assertIn(f"Maximum version length for this hit: {hit['size_budget']}", system)
        self.assertEqual(game.state['hits'][-1]['size_budget'], 80)

    def test_size_repair_runs_once_and_records_remaining_overage(self):
        with patch.object(rally.Player, 'call', side_effect=[reply('x' * 180), reply('y' * 150)]) as call:
            game = self.play(1)
        self.assertEqual(call.call_count, 2)
        self.assertIn('exceeded the character limit', call.call_args.args[0])
        self.assertEqual(game.state['hits'][0]['version'], 'y' * 150)
        self.assertTrue(game.state['hits'][0]['over_budget'])
        self.assertEqual(game.state['faults'], [])
        rally.write_outputs(game)
        self.assertIn('remained over budget: 1', (self.directory / 'final.md').read_text())

    def test_unparsed_output_retries_with_reminder_then_opponent_covers(self):
        with patch.object(rally.Player, 'call', side_effect=['prose', '{broken', reply()]) as call:
            game = self.play(1)
        self.assertEqual(call.call_count, 3)
        self.assertIn('Reply with only the JSON object', call.call_args_list[1].args[0])
        rally.time.sleep.assert_called_once_with(5)
        self.assertEqual(len(game.state['faults']), 1)
        self.assertEqual(game.state['hits'][0]['side'], 1)
        self.assertEqual(game.state['hits'][0]['version'], 'A concise idea')

    def test_fatal_error_stops_without_retry_and_keeps_partial_artifact(self):
        with patch.object(rally.Player, 'call', side_effect=RuntimeError('context length exceeded')) as call:
            game = self.play()
        self.assertEqual(call.call_count, 1)
        rally.time.sleep.assert_not_called()
        self.assertEqual(game.state['status'], 'error')
        rally.write_outputs(game)
        final = (self.directory / 'final.md').read_text()
        self.assertIn('No completed turns yet', final)
        self.assertIn('context length exceeded', final)

    def test_notes_are_ordered_consumed_once_and_persist_after_resume(self):
        captured = []

        def player(system, user):
            captured.append(user)
            if len(captured) == 1:
                rally.append_note(self.directory, 'First owner constraint\nKeep this wording.')
                rally.append_note(self.directory, 'Second owner constraint')
                return reply()
            raise KeyboardInterrupt()

        with patch.object(rally.Player, 'call', side_effect=player):
            game = self.play(3)
        self.assertEqual(game.state['status'], 'stopped')
        self.assertIn('First owner constraint\nKeep this wording.', captured[1])
        self.assertLess(captured[1].index('First owner constraint'), captured[1].index('Second owner constraint'))
        self.assertEqual(list((self.directory / 'inbox').glob('*.md')), [])
        with patch.object(rally.Player, 'call', return_value=reply()) as call, \
                patch.object(rally, 'preflight_players', return_value=True):
            self.assertEqual(rally.resume_command(['--dir', str(self.directory)]), 0)
        self.assertEqual(call.call_count, 2)
        for invocation in call.call_args_list:
            self.assertIn('First owner constraint\nKeep this wording.', invocation.args[1])
            self.assertIn('Second owner constraint', invocation.args[1])
        _, state = rally.load_state()
        self.assertEqual([hit['n'] for hit in state['hits']], [1, 2, 3])
        self.assertEqual([hit['side'] for hit in state['hits']], [0, 1, 0])
        events = [json.loads(line) for line in (self.directory / 'events.jsonl').read_text().splitlines()]
        self.assertEqual([event['id'] for event in events], list(range(1, len(events) + 1)))
        self.assertEqual(sum(event['type'] == 'note' for event in events), 2)
        self.assertEqual(sum(event['type'] == 'resume' for event in events), 1)

    def test_live_engine_cannot_be_resumed_from_another_process(self):
        game = rally.Rally('An idea', 4, self.players, self.directory)
        before = (self.directory / 'state.json').read_bytes()
        with rally.rally_lock(self.directory):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), 'resume', '--dir', str(self.directory)],
                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn('active engine', result.stderr)
        self.assertEqual((self.directory / 'state.json').read_bytes(), before)

    def test_preflight_failure_creates_no_rally(self):
        output = self.directory / 'not-started'
        args = ['rally.py', '--idea', 'test', '--players', 'mock:left,mock:right',
                '--out', str(output), '--no-animation']
        with patch.object(sys, 'argv', args), \
                patch.object(rally.Player, 'call', return_value='not JSON') as call, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(rally.main(), 1)
        self.assertEqual(call.call_count, 2)
        self.assertFalse(output.exists())

    def test_default_count_is_ten_and_explicit_count_overrides_it(self):
        for count in (None, 2):
            output = self.directory / ('default' if count is None else 'explicit')
            args = ['rally.py', '--idea', 'test', '--players', 'mock:left,mock:right',
                    '--out', str(output), '--no-animation']
            if count is not None:
                args.extend(['-n', str(count)])
            with patch.object(sys, 'argv', args):
                self.assertEqual(rally.main(), 0)
            state = rally.load_state(output)[1]
            self.assertEqual(len(state['hits']), 10 if count is None else count)


if __name__ == '__main__':
    unittest.main()
