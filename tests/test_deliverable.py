"""Contracts for one refined outcome and honoured output instructions (#12).

Credential-free mocks only. The engine never picks an output template: it relays
the owner's brief verbatim to every hit and reports which questions survived.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_rally import rally, SCRIPT

PLAIN = 'A habit tracker for amateur bands'
PLAN = PLAIN + '\n\nReturn it as a six-month plan with milestones, in Finnish, under 400 words.'
BUILD = PLAIN + '\n\nGive me a one-shot build prompt for a coding agent.'


def reply(version='A concise idea', questions=None):
    return json.dumps({'version': version, 'critique': 'ok', 'changes': ['Tightened it'],
                       'open_questions': questions or [], 'owner_conflicts': []})


class BriefCarryingTests(unittest.TestCase):
    """An explicit format request is part of the brief, so it reaches every hit."""

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

    def play(self, brief, scripted, total=4):
        captured = []

        def player(system, user):
            captured.append(user)
            scheduled = scripted[len(captured) - 1]
            if isinstance(scheduled, BaseException):
                raise scheduled
            return scheduled

        with patch.object(rally.Player, 'call', side_effect=player):
            game = rally.play(brief, total, self.players, self.directory, rally.Progress())
        return game, captured

    def final_text(self, game):
        rally.write_outputs(game)
        return (self.directory / 'final.md').read_text(encoding='utf-8')

    def test_requested_format_reaches_every_hit(self):
        game, captured = self.play(PLAN, [reply('v%d' % n) for n in range(1, 5)])
        self.assertEqual(game.state['status'], 'done')
        self.assertEqual(len(captured), 4)
        for n, prompt in enumerate(captured, start=1):
            with self.subTest(hit=n):
                self.assertIn('six-month plan with milestones, in Finnish, under 400 words',
                              prompt)
                self.assertIn('form, language, audience or length', prompt)
        self.assertIn('six-month plan with milestones', self.final_text(game))

    def test_requested_build_prompt_reaches_every_hit(self):
        _, captured = self.play(BUILD, [reply('v%d' % n) for n in range(1, 5)])
        for prompt in captured:
            self.assertIn('one-shot build prompt for a coding agent', prompt)

    def test_plain_brief_adds_no_format_of_its_own(self):
        game, captured = self.play(PLAIN, [reply('v%d' % n) for n in range(1, 5)])
        for prompt in captured:
            self.assertIn(PLAIN, prompt)
            for word in ('build prompt', 'ticket-ready', 'template'):
                self.assertNotIn(word, prompt)
        final = self.final_text(game)
        self.assertTrue(final.startswith('v4'), final[:40])
        self.assertIn('Owner brief (authoritative, as given):', final)
        self.assertIn(PLAIN, final)

    def test_system_prompt_honours_the_brief_over_a_default_shape(self):
        system = rally.SYSTEM.format(me='A', them='B', n=1, total=4, remaining=3,
                                     phase=rally.PHASES['open'], budget=500)
        self.assertIn('form, language, audience or length', system)
        self.assertIn('those instructions outrank your own preference', system)
        self.assertIn('not a build prompt or a ticket spec', system)

    def test_resolved_questions_are_separated_from_still_open_ones(self):
        scripted = [
            reply('v1', ['Which platform first?', 'Who pays for it?']),
            reply('v2', ['Who pays for it?']),
            reply('v3', []),
            reply('v4', ['Who pays for it?', 'Which launch city?']),
        ]
        game, _ = self.play(PLAIN, scripted)
        final = self.final_text(game)
        still, earlier = final.index('still leaves open'), final.index('no longer asks')
        self.assertLess(still, earlier)
        self.assertIn('- Who pays for it?', final[still:earlier])
        self.assertIn('- Which launch city?', final[still:earlier])
        self.assertNotIn('Which platform first?', final[still:earlier])
        self.assertIn('- Which platform first?', final[earlier:])
        self.assertIn('do not invent answers', final[earlier:])
        self.assertEqual(final.count('Who pays for it?'), 1)

    def test_a_rally_without_open_questions_reports_none(self):
        game, _ = self.play(PLAIN, [reply('v%d' % n) for n in range(1, 5)])
        final = self.final_text(game)
        self.assertNotIn('still leaves open', final)
        self.assertNotIn('no longer asks', final)

    def test_an_interrupted_rally_is_identified_as_partial(self):
        scripted = [reply('v1', ['Who pays for it?']), KeyboardInterrupt()]
        game, _ = self.play(PLAIN, scripted)
        self.assertEqual(game.state['status'], 'stopped')
        final = self.final_text(game)
        self.assertTrue(final.startswith('v1'), final[:40])
        self.assertIn('Partial result: the rally ended stopped after 1 of 4 hits', final)
        self.assertIn('not a converged final version', final)
        self.assertIn('Owner brief (authoritative, as given):', final)
        self.assertIn('still leaves open', final)


class SkillContractTests(unittest.TestCase):
    """The documented host flow returns one outcome without an output interview."""

    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'ping-pong'
        self.skill = (root / 'SKILL.md').read_text(encoding='utf-8')
        self.outputs = (root / 'OUTPUTS.md').read_text(encoding='utf-8')

    def test_skill_stays_under_a_hundred_lines(self):
        self.assertLess(len(self.skill.splitlines()), 100)

    def test_skill_keeps_its_name_and_the_seven_steps(self):
        self.assertIn('name: ping-pong', self.skill)
        for step in range(1, 8):
            self.assertIn('\n%d. **' % step, self.skill)

    def test_skill_honours_a_requested_format_and_defaults_to_a_refined_idea(self):
        self.assertIn('Do not ask the user to pick an output format', self.skill)
        self.assertIn('refined idea', self.skill)
        self.assertIn('deliverable.md', self.skill)

    def test_outputs_leads_with_the_default_refined_idea(self):
        self.assertLess(self.outputs.index('Refined idea'),
                        self.outputs.index('One-shot build prompt'))
        self.assertIn('only when the brief asks for it', self.outputs)


if __name__ == '__main__':
    unittest.main()
