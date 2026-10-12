"""Contracts for the unified rally lifecycle (#23). Credential-free mocks only.

Starting and resuming must share one cancellation, error, finalization and exit
code policy, and a loaded rally must be constructed explicitly.
"""
import contextlib
import inspect
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_rally import rally, SCRIPT


def reply(version='A concise idea'):
    return json.dumps({'version': version, 'critique': 'ok', 'changes': ['Tightened it'],
                       'open_questions': [], 'owner_conflicts': []})


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.players = [rally.Player('mock:left'), rally.Player('mock:right')]
        self.out = io.StringIO()
        for replacement in (patch.object(rally, 'ACTIVE', self.directory / 'active.json'),
                            patch.object(sys, 'path', [str(SCRIPT.parent)] + sys.path),
                            patch.object(rally.time, 'sleep'),
                            contextlib.redirect_stdout(self.out)):
            replacement.__enter__()
            self.addCleanup(replacement.__exit__, None, None, None)

    def play(self, out=None, total=4):
        target = out or self.directory
        target.mkdir(parents=True, exist_ok=True)
        return rally.play('An idea worth finishing', total, self.players, target,
                          rally.Progress())

    def final(self, out=None):
        return ((out or self.directory) / 'final.md').read_text(encoding='utf-8')

    # ------------------------------------------------- one policy for both paths

    def test_a_new_rally_records_an_engine_error_instead_of_raising_it(self):
        broken = RuntimeError('the engine itself broke')
        with patch.object(rally, 'consume_notes', side_effect=broken):
            game = self.play()
        self.assertEqual(game.state['status'], 'error')
        self.assertIs(game.error, broken)
        self.assertIsNone(game.state['current'])
        self.assertIsNotNone(game.state['finished_at'])
        self.assertEqual(rally.load_state(self.directory)[1]['status'], 'error')
        self.assertEqual(rally.wait_for_event(self.directory, timeout=0)[0]['type'], 'error')
        self.assertIn('the engine itself broke', self.final())

    def test_an_engine_error_before_the_first_hit_still_leaves_an_artifact(self):
        with patch.object(rally, 'consume_notes', side_effect=RuntimeError('broke on hit one')):
            game = self.play()
        self.assertEqual(game.state['hits'], [])
        self.assertIn('No completed turns yet', self.final())
        self.assertEqual(rally.report_result(game, stream=self.out), 1)

    def test_a_resumed_rally_uses_the_same_error_policy_and_exit_code(self):
        scripted = [reply('v1'), KeyboardInterrupt()]

        def player(system, user):
            scheduled = scripted.pop(0)
            if isinstance(scheduled, BaseException):
                raise scheduled
            return scheduled

        with patch.object(rally.Player, 'call', side_effect=player):
            stopped = self.play()
        self.assertEqual(stopped.state['status'], 'stopped')

        with patch.object(rally, 'consume_notes', side_effect=RuntimeError('broke on resume')), \
                patch.object(rally, 'preflight_players', return_value=True), \
                patch.object(rally.Player, 'call', return_value=reply()), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = rally.resume_rally(self.directory)
        self.assertEqual(code, 1)
        self.assertIn('broke on resume', stderr.getvalue())
        resumed = rally.load_state(self.directory)[1]
        self.assertEqual(resumed['status'], 'error')
        self.assertEqual([hit['n'] for hit in resumed['hits']], [1])
        self.assertIn('broke on resume', self.final())
        self.assertIn('v1', self.final())

    def test_cancellation_is_finalized_the_same_way_on_both_paths(self):
        with patch.object(rally.Player, 'call', side_effect=KeyboardInterrupt()):
            started = self.play()
        self.assertEqual(started.state['status'], 'stopped')
        self.assertEqual(rally.wait_for_event(self.directory, timeout=0)[0]['type'], 'stopped')
        self.assertEqual(rally.report_result(started, stream=self.out), 130)
        events = [json.loads(line) for line
                  in (self.directory / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual([event['id'] for event in events], list(range(1, len(events) + 1)))

        with patch.object(rally.Player, 'call', side_effect=KeyboardInterrupt()), \
                patch.object(rally, 'preflight_players', return_value=True), \
                contextlib.redirect_stderr(io.StringIO()):
            code = rally.resume_rally(self.directory)
        self.assertEqual(code, 130)
        resumed = rally.load_state(self.directory)[1]
        self.assertEqual(resumed['status'], 'stopped')
        self.assertTrue((self.directory / 'final.md').exists())

    def test_a_rally_that_never_started_is_reported_not_finalized(self):
        first = self.play()
        self.assertEqual(first.state['status'], 'done')
        with self.assertRaises(FileExistsError):
            self.play()
        # The finished rally's own state and events survive the refused start.
        self.assertEqual(rally.load_state(self.directory)[1], first.state)

    def test_report_result_maps_every_terminal_state_to_its_exit_code(self):
        game = self.play()
        for status, expected in (('done', 0), ('stopped', 130), ('error', 1)):
            with self.subTest(status=status):
                game.state['status'] = status
                self.assertEqual(rally.report_result(game, stream=self.out), expected)

    # ------------------------------------------------- explicit restoration path

    def test_load_restores_a_saved_rally_without_reseeding_or_resetting(self):
        (self.directory / 'constraints.md').write_text('- A fresh constraint\n', encoding='utf-8')
        saved = {'idea': 'An idea', 'iterations': 4, 'players': [], 'status': 'stopped',
                 'hits': [{'n': 1, 'side': 0}], 'event_id': 7, 'next_side': 1,
                 'owner_notes': ['Keep this'], 'consumed_notes': ['note-000000001'],
                 'ledger': [{'id': 'O-1', 'by': 'owner', 'text': 'An older constraint',
                             'status': 'standing', 'reason': None}],
                 'disputes': [{'n': 1}], 'current': None}
        loaded = rally.Rally.load(self.directory, saved)
        self.assertTrue(loaded.started)
        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.out, self.directory)
        self.assertEqual([entry['text'] for entry in loaded.state['ledger']],
                         ['An older constraint'], 'constraints.md must not be re-seeded')
        self.assertEqual(loaded.state['event_id'], 7)
        self.assertEqual(loaded.state['next_side'], 1)
        self.assertEqual(loaded.state['owner_notes'], ['Keep this'])
        self.assertEqual(loaded.state['consumed_notes'], ['note-000000001'])
        self.assertEqual(loaded.state['disputes'], [{'n': 1}])
        self.assertEqual([hit['n'] for hit in loaded.state['hits']], [1])

    def test_load_defaults_the_collections_an_older_rally_may_lack(self):
        loaded = rally.Rally.load(self.directory, {'idea': 'x', 'iterations': 2, 'players': []})
        for key in ('hits', 'faults', 'owner_notes', 'consumed_notes', 'ledger', 'disputes'):
            self.assertEqual(loaded.state[key], [], key)

    # ------------------------------------------------- one reply, one retry policy

    def test_fetch_reply_owns_the_retry_and_the_size_repair(self):
        ticker = rally.Progress()
        player = self.players[0]
        with patch.object(player, 'call', side_effect=['not JSON', reply('ok')]) as call:
            found, err, fatal, over = rally.fetch_reply(player, 'sys', 'user', 500, ticker)
        self.assertEqual(call.call_count, 2, 'exactly one retry for an unparsed reply')
        self.assertEqual(found['version'], 'ok')
        self.assertFalse(fatal or over)

        with patch.object(player, 'call', side_effect=[reply('x' * 40), reply('short')]) as call:
            found, _, _, over = rally.fetch_reply(player, 'sys', 'user', 10, ticker)
        self.assertEqual(call.call_count, 2, 'exactly one rewrite attempt for an overage')
        self.assertEqual(found['version'], 'short')
        self.assertFalse(over)

        with patch.object(player, 'call', side_effect=[reply('x' * 40), reply('x' * 30)]):
            found, _, _, over = rally.fetch_reply(player, 'sys', 'user', 10, ticker)
        self.assertTrue(over, 'a remaining overage is flagged, not retried again')

        with patch.object(player, 'call', side_effect=RuntimeError('context length exceeded')) as call:
            found, err, fatal, over = rally.fetch_reply(player, 'sys', 'user', 500, ticker)
        self.assertEqual(call.call_count, 1, 'a fatal error is never retried')
        self.assertIsNone(found)
        self.assertTrue(fatal)
        self.assertIn('context length exceeded', err)

    def test_the_turn_loop_no_longer_carries_an_unused_duration_average(self):
        self.assertEqual(list(inspect.signature(rally.Progress.fly).parameters),
                         ['self', 'n', 'total', 'side'])
        source = inspect.getsource(rally.play_turns)
        self.assertNotIn('durations', source)
        game = self.play(total=2)
        for hit in game.state['hits']:
            self.assertIsInstance(hit['seconds'], float)
        self.assertIn('in 0s', self.out.getvalue())

    def test_terminate_as_cancel_restores_the_previous_handler(self):
        if not hasattr(signal, 'SIGTERM'):  # pragma: no cover - POSIX and Windows both have it
            self.skipTest('no SIGTERM on this platform')
        before = signal.getsignal(signal.SIGTERM)
        with rally.terminate_as_cancel():
            handler = signal.getsignal(signal.SIGTERM)
            self.assertNotEqual(handler, before)
            with self.assertRaises(KeyboardInterrupt):
                handler(signal.SIGTERM, None)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)


if __name__ == '__main__':
    unittest.main()
