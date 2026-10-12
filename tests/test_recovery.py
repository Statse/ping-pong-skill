"""Contracts for the engine features recovered from overlapping agent work."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_rally import rally, SCRIPT


def reply(version='A concise idea'):
    return json.dumps({'version': version, 'critique': 'ok', 'changes': [],
                       'open_questions': [], 'owner_conflicts': []})


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.real_sleep = time.sleep
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

    def test_process_crash_resume_keeps_completed_hits_and_releases_lock(self):
        output = self.directory / 'crashed-run'
        environment = dict(os.environ, HOME=str(self.directory), USERPROFILE=str(self.directory))
        process = subprocess.Popen(
            [sys.executable, str(SCRIPT), '--idea', 'A small idea', '-n', '2',
             '--players', 'mock:left,mock:right', '--no-animation', '--out', str(output)],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Poll with real time while the subprocess runs independently of patched sleeps.
        with patch.object(rally.time, 'sleep', wraps=self.real_sleep):
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if (output / 'state.json').exists():
                        state = rally.load_state(output)[1]
                        if len(state['hits']) == 1 and (state.get('current') or {}).get('n') == 2:
                            break
                    if process.poll() is not None:
                        self.fail('mock engine exited before it could be interrupted')
                    self.real_sleep(0.05)
                else:
                    self.fail('mock engine did not reach the second hit')
                completed = state['hits'][0]
                process.kill()
                process.communicate(timeout=5)
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), 'resume', '--dir', str(output)],
                    env=environment, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                resumed = rally.load_state(output)[1]
                self.assertEqual(resumed['hits'][0], completed)
                self.assertEqual([hit['n'] for hit in resumed['hits']], [1, 2])
                self.assertEqual(resumed['status'], 'done')
                events = [json.loads(line) for line in (output / 'events.jsonl').read_text().splitlines()]
                self.assertEqual([event['type'] for event in events], ['serve', 'hit', 'resume', 'hit', 'done'])
                self.assertEqual([event['id'] for event in events], [1, 2, 3, 4, 5])
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate()

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


class OwnerNoteDurabilityTests(unittest.TestCase):
    """Issue #11: a queued note must be delivered exactly once, in submission order."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.players = [rally.Player('mock:left'), rally.Player('mock:right')]
        for replacement in (patch.object(rally, 'ACTIVE', self.directory / 'active.json'),
                            contextlib.redirect_stdout(io.StringIO())):
            replacement.__enter__()
            self.addCleanup(replacement.__exit__, None, None, None)
        self.game = rally.Rally('An idea', 4, self.players, self.directory)
        self.inbox = self.directory / 'inbox'

    def reload(self):
        """A fresh engine over the committed state, as resume builds one."""
        _, state = rally.load_state(self.directory)
        return rally.Rally.load(self.directory, state)

    def note_events(self):
        events = [json.loads(line) for line in
                  (self.directory / 'events.jsonl').read_text().splitlines()]
        return [event for event in events if event['type'] == 'note']

    def test_interruption_after_the_commit_does_not_redeliver_the_note(self):
        rally.append_note(self.directory, 'Keep the owner wording')
        queued = list(self.inbox.glob('note-*.md'))
        self.assertEqual(len(queued), 1)
        # Commit the note, then fail before the inbox file can be archived.
        with patch.object(rally, 'archive_note', side_effect=OSError('crash')):
            with self.assertRaises(OSError):
                rally.consume_notes(self.game)
        self.assertTrue(queued[0].is_file())

        resumed = self.reload()
        self.assertEqual(rally.consume_notes(resumed), ['Keep the owner wording'])
        self.assertEqual(len(self.note_events()), 1)
        self.assertEqual(list(self.inbox.glob('note-*.md')), [])
        self.assertTrue((self.inbox / 'consumed' / queued[0].name).is_file())

    def test_interruption_before_the_commit_keeps_the_note(self):
        rally.append_note(self.directory, 'Survive the crash')
        with patch.object(rally.Rally, 'save', side_effect=OSError('crash')):
            with self.assertRaises(OSError):
                rally.consume_notes(self.game)
        resumed = self.reload()
        self.assertEqual(rally.consume_notes(resumed), ['Survive the crash'])
        self.assertEqual(len(self.note_events()), 1)

    def test_two_identical_notes_are_both_preserved(self):
        rally.append_note(self.directory, 'Same text')
        rally.append_note(self.directory, 'Same text')
        self.assertEqual(rally.consume_notes(self.game), ['Same text', 'Same text'])
        self.assertEqual(len(self.note_events()), 2)
        self.assertEqual(len(self.game.state['consumed_notes']), 2)

    def test_submission_order_survives_a_clock_without_resolution(self):
        with patch.object(rally.time, 'time_ns', return_value=1):
            for index in range(1, 13):
                rally.append_note(self.directory, f'Note {index:02d}')
        delivered = rally.consume_notes(self.game)
        self.assertEqual(delivered, [f'Note {index:02d}' for index in range(1, 13)])

    def test_legacy_pending_notes_are_consumed_once_and_ordered_first(self):
        self.inbox.mkdir(exist_ok=True)
        for stamp, text in ((7, 'Older legacy note'), (9, 'Newer legacy note')):
            (self.inbox / f'note-{stamp:020d}-abc.md').write_text(text, encoding='utf-8')
        del self.game.state['consumed_notes']
        rally.append_note(self.directory, 'Current note')
        self.assertEqual(rally.consume_notes(self.game),
                         ['Older legacy note', 'Newer legacy note', 'Current note'])
        self.assertEqual(rally.consume_notes(self.reload()),
                         ['Older legacy note', 'Newer legacy note', 'Current note'])
        self.assertEqual(len(self.note_events()), 3)

    def test_a_reserved_name_without_text_waits_instead_of_being_lost(self):
        self.inbox.mkdir(exist_ok=True)
        reserved = self.inbox / rally.note_name(rally.next_note_seq(self.inbox, self.game.state))
        reserved.touch()
        self.assertEqual(rally.consume_notes(self.game), [])
        self.assertTrue(reserved.is_file())
        reserved.write_text('Written late', encoding='utf-8')
        self.assertEqual(rally.consume_notes(self.game), ['Written late'])

    def test_a_note_is_never_visible_half_written(self):
        """The claimed name holds nothing or the whole note, never a prefix."""
        multiline = 'First line of the note\nSecond line\nThird line ää 🏓'
        seen = []
        original = rally.os.replace

        def spy(source, destination):
            name = Path(destination).name
            if name.startswith('note-'):
                # The claimed name exists and is still empty until this rename.
                seen.append((Path(destination).read_text(encoding='utf-8'),
                             Path(source).read_text(encoding='utf-8')))
            return original(source, destination)

        with patch.object(rally.os, 'replace', spy):
            rally.append_note(self.directory, multiline)
        self.assertEqual(seen, [('', multiline)])
        self.assertEqual(rally.consume_notes(self.game), [multiline])
        self.assertEqual(list(self.inbox.glob('*.tmp')), [])

    def test_a_later_note_never_reuses_a_consumed_identity(self):
        rally.append_note(self.directory, 'First')
        rally.consume_notes(self.game)
        # Even if the archive is gone, the committed identity still reserves the name.
        shutil.rmtree(self.inbox / 'consumed')
        rally.append_note(self.directory, 'Second')
        self.assertEqual(rally.consume_notes(self.game), ['First', 'Second'])
        self.assertEqual(len(self.note_events()), 2)
