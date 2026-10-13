"""Credential-free regressions for the four whole-project review findings."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_rally import rally


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.out = Path(temporary.name)
        self.players = [rally.Player('mock:left'), rally.Player('mock:right')]
        for replacement in (patch.object(rally, 'ACTIVE', self.out / 'active.json'),
                            patch.object(rally.time, 'sleep'),
                            contextlib.redirect_stdout(io.StringIO())):
            replacement.__enter__()
            self.addCleanup(replacement.__exit__, None, None, None)

    def test_next_model_receives_questions_and_requirement_conflicts(self):
        first = {'version': 'First draft', 'open_questions': ['Who pays?'],
                 'owner_conflicts': [{'item': 'No accounts', 'reason': 'Sync needs identity'}]}
        with patch.object(rally.Player, 'call', side_effect=[
                json.dumps(first), json.dumps({'version': 'Final draft'})]) as call:
            game = rally.play('An idea', 2, self.players, self.out, rally.Progress())
        self.assertEqual(game.state['status'], 'done')
        prompt = call.call_args_list[1].args[1]
        for text in ('Who pays?', 'No accounts', 'Sync needs identity'):
            self.assertIn(text, prompt)
        self.assertIn('not owner approval', prompt)

    def test_pending_earlier_note_blocks_later_note_even_across_resume(self):
        game = rally.Rally('Idea', 2, self.players, self.out)
        inbox = self.out / 'inbox'
        inbox.mkdir(exist_ok=True)
        reserved = inbox / rally.note_name(1)
        reserved.touch()
        rally.append_note(self.out, 'Second')
        self.assertEqual(rally.consume_notes(game), [])
        reserved.write_text('First', encoding='utf-8')
        _, state = rally.load_state(self.out)
        restored = rally.Rally.load(self.out, state)
        self.assertEqual(rally.consume_notes(restored), ['First', 'Second'])
        self.assertEqual(rally.consume_notes(restored), ['First', 'Second'])
        self.assertEqual(len(restored.state['consumed_notes']), 2)

    def test_unreadable_earlier_note_does_not_allow_overtaking(self):
        game = rally.Rally('Idea', 2, self.players, self.out)
        rally.append_note(self.out, 'First')
        rally.append_note(self.out, 'Second')
        original = Path.read_text

        def read(path, *args, **kwargs):
            if path.name == rally.note_name(1):
                raise PermissionError('temporarily unavailable')
            return original(path, *args, **kwargs)

        with patch.object(Path, 'read_text', read):
            self.assertEqual(rally.consume_notes(game), [])
        self.assertEqual(rally.consume_notes(game), ['First', 'Second'])

    def test_concurrent_publisher_cannot_overtake_an_unpublished_note(self):
        game = rally.Rally('Idea', 2, self.players, self.out)
        original = rally.publish
        observed = []

        def publish(staged, destination):
            if Path(destination).name == rally.note_name(1):
                # Interleave another submission and an engine read at the exact
                # point where the first writer has claimed but not published.
                rally.append_note(self.out, 'Second')
                observed.append(rally.consume_notes(game))
            return original(staged, destination)

        with patch.object(rally, 'publish', side_effect=publish):
            rally.append_note(self.out, 'First')
        self.assertEqual(observed, [[]])
        self.assertEqual(rally.consume_notes(game), ['First', 'Second'])

    def test_failed_note_publication_does_not_leave_a_queue_barrier(self):
        game = rally.Rally('Idea', 2, self.players, self.out)
        with patch.object(rally, 'publish', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                rally.append_note(self.out, 'Unsubmitted note')
        self.assertEqual(list((self.out / 'inbox').glob('note-*.md')), [])
        self.assertEqual(list((self.out / 'inbox').glob('pending-*.tmp')), [])
        rally.append_note(self.out, 'Successful note')
        self.assertEqual(rally.consume_notes(game), ['Successful note'])

    def test_prompt_words_do_not_make_transient_cli_errors_fatal(self):
        for failure in ('exit', 'timeout'):
            for repair in (False, True):
                with self.subTest(failure=failure, size_repair=repair):
                    calls = []

                    def run(cmd, stdin, workdir, timeout):
                        calls.append(cmd)
                        if repair and len(calls) == 1:
                            return subprocess.CompletedProcess(cmd, 0, '{"version":"oversized"}', '')
                        if len(calls) == (2 if repair else 1):
                            if failure == 'timeout':
                                raise subprocess.TimeoutExpired(cmd, timeout)
                            return subprocess.CompletedProcess(cmd, 1, '', 'Temporary outage')
                        return subprocess.CompletedProcess(cmd, 0, '{"version":"ok"}', '')

                    with patch.object(rally, 'cli_bin', return_value='/fake/claude'), \
                            patch.object(rally, 'run_cli', side_effect=run):
                        result, error, fatal, over = rally.fetch_reply(
                            rally.Player('cli:claude'), 'System',
                            'An idea about API key authentication and context limits',
                            2 if repair else 100, rally.Progress())
                    self.assertFalse(fatal)
                    self.assertIsNotNone(result)
                    self.assertEqual(result['version'], 'oversized' if repair else 'ok')
                    self.assertEqual(len(calls), 2)
                    if error:
                        self.assertNotIn('An idea about', error)

    def test_real_cli_authentication_failure_still_stops_without_retry(self):
        with patch.object(rally, 'cli_bin', return_value='/fake/claude'), \
                patch.object(rally, 'run_cli', return_value=subprocess.CompletedProcess(
                    ['claude'], 1, '', 'Authentication failed: not logged in')) as run:
            result, error, fatal, _ = rally.fetch_reply(
                rally.Player('cli:claude'), 'System', 'Ordinary idea', 100, rally.Progress())
        self.assertIsNone(result)
        self.assertTrue(fatal)
        self.assertIn('Authentication failed', error)
        self.assertEqual(run.call_count, 1)

    def test_malformed_reply_fields_are_rejected(self):
        malformed = [
            {'version': value} for value in (True, 42, ['draft'], {'draft': 'text'}, ' \n ')
        ]
        for field in ('critique', 'changes', 'open_questions', 'owner_conflicts'):
            malformed.append({'version': 'valid', field: None})
        for field in ('changes', 'open_questions'):
            for value in ('abc', {}, [1], [None], [{'text': 'wrong type'}]):
                malformed.append({'version': 'valid', field: value})
        for value in ('abc', {}, ['conflict'], [{}], [{'item': 'rule', 'reason': 3}]):
            malformed.append({'version': 'valid', 'owner_conflicts': value})
        malformed.append({'version': 'valid', 'critique': ['not text']})
        for payload in malformed:
            with self.subTest(payload=payload):
                self.assertFalse(rally.parse_reply(json.dumps(payload))['parsed'])

    def test_malformed_draft_is_retried_and_never_committed(self):
        with patch.object(rally.Player, 'call', side_effect=[
                '{"version":{"bad":"shape"}}', '{"version":"Valid draft"}']) as call:
            game = rally.play('Idea', 1, self.players, self.out, rally.Progress())
        self.assertEqual(call.call_count, 2)
        self.assertEqual([hit['version'] for hit in game.state['hits']], ['Valid draft'])
        self.assertEqual(game.state['status'], 'done')

    def test_malformed_size_rewrite_keeps_the_original_valid_draft(self):
        with patch.object(rally.Player, 'call', side_effect=[
                '{"version":"Valid but long draft"}', '{"version":true}']) as call:
            result, _, fatal, over = rally.fetch_reply(
                self.players[0], 'System', 'Idea', 5, rally.Progress())
        self.assertEqual(result['version'], 'Valid but long draft')
        self.assertFalse(fatal)
        self.assertTrue(over)
        self.assertEqual(call.call_count, 2)


if __name__ == '__main__':
    unittest.main()
