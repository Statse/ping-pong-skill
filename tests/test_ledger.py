"""Contracts for the durable decision ledger (#5). Credential-free mocks only."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_rally import rally, SCRIPT


def reply(version='A concise idea', decisions=None):
    payload = {'version': version, 'critique': 'ok', 'changes': [],
               'open_questions': [], 'owner_conflicts': []}
    if decisions is not None:
        payload['decisions'] = decisions
    return json.dumps(payload)


def entry(identifier, by, text, status='standing', reason=None):
    return {'id': identifier, 'by': by, 'text': text, 'status': status, 'reason': reason}


class LedgerRenderingTests(unittest.TestCase):
    """Pure rendering: the cap is a prompt budget, never a deletion."""

    def test_forty_entry_fixture_never_evicts_owner_entries(self):
        ledger = ([entry('O-%d' % i, 'owner', 'owner rule %d' % i) for i in range(1, 11)]
                  + [entry('P-%d' % i, 'Mock left', 'player call %d' % i) for i in range(1, 31)])
        shown, over_cap = rally.ledger_view(ledger)
        self.assertFalse(over_cap)
        self.assertEqual(len(shown), rally.LEDGER_CAP)
        self.assertEqual([e['id'] for e in shown if e['by'] == 'owner'],
                         ['O-%d' % i for i in range(1, 11)])
        # Fifteen player slots remain, and they are the newest player entries.
        self.assertEqual([e['id'] for e in shown if e['by'] != 'owner'],
                         ['P-%d' % i for i in range(16, 31)])
        text = rally.render_ledger(ledger)
        for i in range(1, 11):
            self.assertIn('owner rule %d' % i, text)
        self.assertNotIn('player call 1:', text)
        self.assertIn('15 older player entries are omitted', text)
        self.assertNotIn('Cap exception', text)
        self.assertEqual(len(ledger), 40, 'rendering must not mutate state')

    def test_owner_only_overflow_keeps_every_owner_entry_and_states_the_exception(self):
        ledger = ([entry('O-%d' % i, 'owner', 'owner rule %d' % i) for i in range(1, 31)]
                  + [entry('P-1', 'Mock left', 'a player decision')])
        shown, over_cap = rally.ledger_view(ledger)
        self.assertTrue(over_cap)
        self.assertEqual([e['id'] for e in shown], ['O-%d' % i for i in range(1, 31)])
        text = rally.render_ledger(ledger)
        self.assertIn('Cap exception', text)
        self.assertIn('every owner entry is listed', text)
        self.assertIn('owner rule 30', text)

    def test_rendered_ledger_names_the_rules_players_must_follow(self):
        text = rally.render_ledger([entry('O-1', 'owner', 'Keep it offline'),
                                    entry('P-1', 'Mock left', 'Ship a CLI first'),
                                    entry('P-2', 'Mock right', 'Drop the web UI',
                                          'dropped', 'out of scope')])
        self.assertIn('cannot be dropped', text)
        self.assertIn('requires a reason', text)
        self.assertIn('- O-1 (owner): Keep it offline', text)
        self.assertIn('- P-1 (Mock left): Ship a CLI first', text)
        self.assertIn('[dropped: out of scope]', text)

    def test_empty_ledger_is_rendered_rather_than_hidden(self):
        self.assertIn('(empty: no decisions recorded yet)', rally.render_ledger([]))


class SeedingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def test_constraints_bullets_become_numbered_owner_entries(self):
        (self.directory / 'constraints.md').write_text(
            '- Must run offline\n\n*   Python 3.9 floor\n+ No new dependencies\n'
            'Keep the CLI ää 🏓\n   \n', encoding='utf-8')
        seeded = rally.seed_owner_ledger(self.directory)
        self.assertEqual([e['id'] for e in seeded], ['O-1', 'O-2', 'O-3', 'O-4'])
        self.assertEqual([e['text'] for e in seeded],
                         ['Must run offline', 'Python 3.9 floor', 'No new dependencies',
                          'Keep the CLI ää 🏓'])
        self.assertTrue(all(e['by'] == 'owner' and e['status'] == 'standing'
                            and e['reason'] is None for e in seeded))

    def test_missing_or_empty_constraints_file_is_valid(self):
        self.assertEqual(rally.seed_owner_ledger(self.directory), [])
        (self.directory / 'constraints.md').write_text('\n  \n', encoding='utf-8')
        self.assertEqual(rally.seed_owner_ledger(self.directory), [])


class ReplyProtocolTests(unittest.TestCase):
    def test_decisions_are_parsed_and_junk_is_ignored(self):
        parsed = rally.parse_reply(json.dumps({
            'version': 'v',
            'decisions': [{'op': 'add', 'text': ' Ship a CLI '},
                          {'op': 'drop', 'id': 'P-1', 'reason': 'superseded'},
                          {'op': 'merge', 'id': 'P-2'},
                          'not a dict', None, 42, {'id': 'P-3'}]}))
        self.assertTrue(parsed['parsed'])
        self.assertEqual(parsed['decisions'],
                         [{'op': 'add', 'id': '', 'text': 'Ship a CLI', 'reason': ''},
                          {'op': 'drop', 'id': 'P-1', 'text': '', 'reason': 'superseded'}])

    def test_malformed_decisions_do_not_change_parsed_semantics(self):
        for value in ('nonsense', {'op': 'add'}, 7, None):
            with self.subTest(value=value):
                parsed = rally.parse_reply(json.dumps({'version': 'v', 'decisions': value}))
                self.assertTrue(parsed['parsed'])
                self.assertEqual(parsed['decisions'], [])
        unparsed = rally.parse_reply('prose, no JSON')
        self.assertFalse(unparsed['parsed'])
        self.assertEqual(unparsed['decisions'], [])

    def test_replies_without_decisions_behave_as_before(self):
        parsed = rally.parse_reply(json.dumps({'version': 'v', 'changes': ['one']}))
        self.assertTrue(parsed['parsed'])
        self.assertEqual(parsed['decisions'], [])
        self.assertEqual(parsed['changes'], ['one'])

    def test_system_envelope_advertises_decisions(self):
        system = rally.SYSTEM.format(me='A', them='B', n=1, total=4, remaining=3,
                                     phase=rally.PHASES['open'], budget=500)
        self.assertIn('"decisions"', system)
        self.assertIn('"op": "drop"', system)
        self.assertIn('cannot drop them', system)


class LedgerRallyTests(unittest.TestCase):
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

    def constraints(self, *items):
        (self.directory / 'constraints.md').write_text(
            ''.join('- %s\n' % item for item in items), encoding='utf-8')

    def play(self, total=4):
        return rally.play('An idea that preserves the owner requirements', total,
                          self.players, self.directory, rally.Progress())

    def final_text(self, game):
        rally.write_outputs(game)
        return (self.directory / 'final.md').read_text(encoding='utf-8')

    def events(self):
        return [json.loads(line) for line
                in (self.directory / 'events.jsonl').read_text(encoding='utf-8').splitlines()]

    # ---------------------------------------------------------------- acceptance

    def test_owner_entry_drop_is_refused_and_the_rally_continues(self):
        self.constraints('The rally engine stays standard library only')
        scripted = [
            reply('v1', [{'op': 'drop', 'id': 'O-1', 'reason': 'a dependency would be faster'}]),
            reply('v2'), reply('v3'), reply('v4'),
        ]
        with patch.object(rally.Player, 'call', side_effect=scripted):
            game = self.play(4)
        self.assertEqual(game.state['status'], 'done')
        self.assertEqual(len(game.state['hits']), 4)
        self.assertEqual(game.state['faults'], [])
        owner = game.state['ledger'][0]
        self.assertEqual((owner['id'], owner['status'], owner['reason']), ('O-1', 'standing', None))
        self.assertEqual(len(game.state['disputes']), 1)
        dispute = game.state['disputes'][0]
        self.assertEqual((dispute['n'], dispute['player'], dispute['id'], dispute['op']),
                         (1, 'Mock left', 'O-1', 'drop'))
        self.assertEqual(dispute['reason'], 'a dependency would be faster')
        self.assertIn('owner non-negotiables cannot be dropped', dispute['refused'])
        stored = json.loads((self.directory / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual(stored['disputes'], game.state['disputes'])
        final = self.final_text(game)
        self.assertIn('Ledger disputes', final)
        self.assertIn('owner non-negotiables cannot be dropped', final)
        self.assertIn('a dependency would be faster', final)
        self.assertIn('O-1 (owner non-negotiable): The rally engine stays standard library only',
                      final)
        self.assertIn('ledger', [event['type'] for event in self.events()])

    def test_drop_without_a_reason_is_rejected_and_reported(self):
        scripted = [
            reply('v1', [{'op': 'add', 'text': 'Ship a CLI before any web UI'}]),
            reply('v2', [{'op': 'drop', 'id': 'P-1'}]),
        ]
        with patch.object(rally.Player, 'call', side_effect=scripted):
            game = self.play(2)
        self.assertEqual(game.state['status'], 'done')
        self.assertEqual(game.state['faults'], [])
        self.assertEqual([(e['id'], e['status']) for e in game.state['ledger']],
                         [('P-1', 'standing')])
        self.assertEqual(len(game.state['disputes']), 1)
        self.assertEqual(game.state['disputes'][0]['refused'], 'a drop requires a reason')
        final = self.final_text(game)
        self.assertIn('a drop requires a reason', final)
        self.assertIn('P-1 (Mock left): Ship a CLI before any web UI', final)

    def test_ledger_reaches_every_player_on_every_hit(self):
        self.constraints('Owner rule: keep the engine dependency free')
        prompts = []

        def player(system, user):
            prompts.append(user)
            if len(prompts) == 1:
                return reply('v1', [{'op': 'add', 'text': 'Decided on a single JSON envelope'}])
            return reply('v%d' % len(prompts))

        with patch.object(rally.Player, 'call', side_effect=player):
            game = self.play(4)
        self.assertEqual(game.state['status'], 'done')
        self.assertEqual(len(prompts), 4)
        for n, prompt in enumerate(prompts, 1):
            self.assertIn('Decision ledger', prompt, 'hit %d missed the ledger' % n)
            self.assertIn('O-1 (owner): Owner rule: keep the engine dependency free', prompt)
            self.assertIn('cannot be dropped', prompt)
        # The serve shows no player entry yet; every later hit carries the new one.
        self.assertNotIn('single JSON envelope', prompts[0])
        for prompt in prompts[1:]:
            self.assertIn('P-1 (Mock left): Decided on a single JSON envelope', prompt)

    def test_rally_without_constraints_runs_with_an_empty_owner_ledger(self):
        prompts = []

        def player(system, user):
            prompts.append(user)
            return reply('v%d' % len(prompts))

        with patch.object(rally.Player, 'call', side_effect=player):
            game = self.play(2)
        self.assertFalse((self.directory / 'constraints.md').exists())
        self.assertEqual(game.state['status'], 'done')
        self.assertEqual(game.state['ledger'], [])
        self.assertEqual(game.state['disputes'], [])
        self.assertIn('(empty: no decisions recorded yet)', prompts[0])
        self.assertNotIn('Decisions standing at the end', self.final_text(game))

    def test_final_output_retains_every_decision_that_was_not_dropped(self):
        self.constraints('Stay offline by default', 'Python 3.9 floor')
        scripted = [
            reply('v1', [{'op': 'add', 'text': 'One JSON envelope for every reply'},
                         {'op': 'add', 'text': 'A throwaway decision'}]),
            reply('v2', [{'op': 'add', 'text': 'Events are the audit trail'},
                         {'op': 'drop', 'id': 'P-2', 'reason': 'superseded by P-3'},
                         {'op': 'drop', 'id': 'P-9', 'reason': 'never existed'},
                         {'op': 'drop', 'id': 'P-2', 'reason': 'already gone'}]),
        ]
        with patch.object(rally.Player, 'call', side_effect=scripted):
            game = self.play(2)
        self.assertEqual(game.state['status'], 'done')
        self.assertEqual([(e['id'], e['by'], e['status']) for e in game.state['ledger']],
                         [('O-1', 'owner', 'standing'), ('O-2', 'owner', 'standing'),
                          ('P-1', 'Mock left', 'standing'), ('P-2', 'Mock left', 'dropped'),
                          ('P-3', 'Mock right', 'standing')])
        self.assertEqual(game.state['ledger'][3]['reason'], 'superseded by P-3')
        self.assertEqual([d['refused'] for d in game.state['disputes']],
                         ['no such ledger entry', 'entry was already dropped'])
        final = self.final_text(game)
        for kept in ('O-1 (owner non-negotiable): Stay offline by default',
                     'O-2 (owner non-negotiable): Python 3.9 floor',
                     'P-1 (Mock left): One JSON envelope for every reply',
                     'P-3 (Mock right): Events are the audit trail'):
            self.assertIn(kept, final)
        self.assertIn('Decisions dropped during the rally', final)
        self.assertIn('A throwaway decision — dropped because: superseded by P-3', final)
        self.assertIn('no such ledger entry', final)

    def test_resumed_rally_keeps_its_ledger_and_keeps_delivering_it(self):
        self.constraints('Never lose a completed hit')
        calls = []

        def player(system, user):
            calls.append(user)
            if len(calls) == 1:
                # Long enough that the later hits stay inside their size budgets.
                return reply('x' * 150, [{'op': 'add', 'text': 'Resume must be idempotent'}])
            raise KeyboardInterrupt()

        with patch.object(rally.Player, 'call', side_effect=player):
            game = self.play(3)
        self.assertEqual(game.state['status'], 'stopped')
        before = [dict(e) for e in game.state['ledger']]
        self.assertEqual([e['id'] for e in before], ['O-1', 'P-1'])

        with patch.object(rally.Player, 'call', return_value=reply('y' * 150)) as call, \
                patch.object(rally, 'preflight_players', return_value=True):
            self.assertEqual(rally.resume_command(['--dir', str(self.directory)]), 0)
        self.assertEqual(call.call_count, 2)
        _, state = rally.load_state(self.directory)
        self.assertEqual(state['ledger'], before, 'resume re-seeded or lost the ledger')
        for invocation in call.call_args_list:
            prompt = invocation.args[1]
            self.assertIn('O-1 (owner): Never lose a completed hit', prompt)
            self.assertIn('P-1 (Mock left): Resume must be idempotent', prompt)
        self.assertIn('P-1 (Mock left): Resume must be idempotent',
                      (self.directory / 'final.md').read_text(encoding='utf-8'))

    def test_ledger_changes_are_events_and_never_fault_the_rally(self):
        scripted = [
            reply('v1', [{'op': 'add', 'text': 'A real decision'},
                         {'op': 'add', 'text': '   '},
                         {'op': 'drop', 'id': 'O-7', 'reason': 'no owner entry exists'}]),
            reply('v2'),
        ]
        with patch.object(rally.Player, 'call', side_effect=scripted):
            game = self.play(2)
        self.assertEqual(game.state['status'], 'done')
        self.assertEqual(game.state['faults'], [])
        self.assertEqual([event['type'] for event in self.events()],
                         ['serve', 'hit', 'ledger', 'hit', 'done'])
        ledger_event = [e for e in self.events() if e['type'] == 'ledger'][0]
        self.assertEqual((ledger_event['added'], ledger_event['dropped']), (['P-1'], []))
        self.assertEqual(len(ledger_event['disputed']), 2)
        self.assertEqual([e['id'] for e in self.events()], [1, 2, 3, 4, 5])
        self.assertEqual([d['refused'] for d in game.state['disputes']],
                         ['an added decision needs text',
                          'owner non-negotiables cannot be dropped'])

    def test_hit_event_is_published_against_state_that_has_its_decisions(self):
        """No window where a completed hit is durable but its decisions are not."""
        self.constraints('Keep the engine standard library only')
        scripted = [
            reply('v1', [{'op': 'add', 'text': 'One JSON envelope for every reply'},
                         {'op': 'drop', 'id': 'O-1', 'reason': 'a dependency would be faster'}]),
            reply('v2'),
        ]
        original_open = Path.open
        observed = []

        def observe(path, mode='r', *args, **kwargs):
            if path.name == 'events.jsonl' and mode == 'a':
                observed.append(json.loads(
                    (self.directory / 'state.json').read_text(encoding='utf-8')))
            return original_open(path, mode, *args, **kwargs)

        with patch.object(rally.Player, 'call', side_effect=scripted), \
                patch.object(Path, 'open', observe):
            game = self.play(2)
        self.assertEqual(game.state['status'], 'done')
        self.assertEqual([event['type'] for event in self.events()],
                         ['serve', 'hit', 'ledger', 'hit', 'done'])
        # observed[i] is the state already on disk when event i + 1 was appended.
        serve, first_hit = observed[0], observed[1]
        self.assertEqual([e['id'] for e in serve['ledger']], ['O-1'])
        self.assertEqual(serve['disputes'], [])
        self.assertEqual(len(first_hit['hits']), 1)
        self.assertEqual([e['id'] for e in first_hit['ledger']], ['O-1', 'P-1'])
        self.assertEqual([d['id'] for d in first_hit['disputes']], ['O-1'])
        self.assertEqual(first_hit['event_id'], 2)
        # The ledger event never precedes the state that explains it.
        self.assertEqual(observed[2]['ledger'], first_hit['ledger'])
        self.assertEqual(observed[2]['event_id'], 3)
        self.assertEqual([state['event_id'] for state in observed], [1, 2, 3, 4, 5])

    def test_status_line_surfaces_the_standing_ledger_size(self):
        self.constraints('Keep it small')
        with patch.object(rally.Player, 'call',
                          side_effect=[reply('v1', [{'op': 'add', 'text': 'A decision'}])]):
            game = self.play(1)
        self.assertIn('Ledger: 2 standing.', rally.status_text(game.state))
        self.assertIn('Rally done: 1/1 turns completed.', rally.status_text(game.state))


if __name__ == '__main__':
    unittest.main()
