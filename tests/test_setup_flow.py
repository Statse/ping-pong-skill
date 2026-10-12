"""The documented host sequence (#22): fresh directory, seeded constraints, launch.

Credential-free: the rally runs on mock players through the real CLI entry point.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_rally import rally, SCRIPT


class SetupFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.home = self.workspace / "home"
        self.home.mkdir()
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def run_rally(self, *argv, **kwargs):
        environment = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                           PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, str(SCRIPT)] + [str(a) for a in argv],
                              capture_output=True, text=True, timeout=120,
                              cwd=str(self.workspace), env=environment, **kwargs)

    def documented_sequence(self, *constraints):
        """Exactly the steps in SKILL.md, with the directory captured from setup."""
        brief = self.workspace / "idea.md"
        brief.write_text("A note-taking app for field biologists\n", encoding="utf-8")
        seeding = []
        for constraint in constraints:
            seeding += ["--constraint", constraint]
        prepared = self.run_rally("setup", "--idea-file", "idea.md", *seeding)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        directory = Path(prepared.stdout.strip())
        self.assertTrue(directory.is_dir(),
                        "stdout=%r stderr=%r" % (prepared.stdout, prepared.stderr))
        started = self.run_rally("--idea-file", "idea.md", "-n", 2,
                                 "--players", "mock:left,mock:right", "--out", directory)
        self.assertEqual(started.returncode, 0, started.stderr)
        return directory, started

    def prompts(self, directory):
        state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
        return state, [hit["prompt"] for hit in state["hits"] if "prompt" in hit]

    def test_setup_prints_a_fresh_directory_the_host_can_launch_with(self):
        directory, started = self.documented_sequence("Must work offline",
                                                      "No account required")
        self.assertIn(str(directory), started.stdout)
        state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["id"] for entry in state["ledger"]], ["O-1", "O-2"])
        self.assertEqual([entry["text"] for entry in state["ledger"]],
                         ["Must work offline", "No account required"])
        self.assertTrue(all(entry["by"] == "owner" for entry in state["ledger"]))
        self.assertEqual(len(state["hits"]), 2)

    def test_setup_prints_an_absolute_directory(self):
        """A relative path is unusable to a host that launches from elsewhere."""
        (self.workspace / "idea.md").write_text("An idea\n", encoding="utf-8")
        prepared = self.run_rally("setup", "--idea-file", "idea.md")
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        printed = prepared.stdout.strip()
        self.assertTrue(os.path.isabs(printed), printed)
        self.assertTrue(Path(printed).is_dir(), printed)
        requested = self.run_rally("setup", "--idea", "An idea", "--out", "named-rally")
        self.assertEqual(requested.returncode, 0, requested.stderr)
        self.assertTrue(os.path.isabs(requested.stdout.strip()), requested.stdout)
        self.assertTrue((self.workspace / "named-rally").is_dir())

    def test_owner_constraints_and_brief_reach_every_player_prompt(self):
        captured = []

        def player(system, user):
            captured.append(user)
            return json.dumps({"version": "A version", "critique": "ok", "changes": [],
                               "open_questions": [], "owner_conflicts": [],
                               "decisions": [{"op": "drop", "id": "O-1",
                                              "reason": "too limiting"}]})

        directory = self.workspace / "rally"
        self.assertEqual(rally.setup_command(
            ["--idea", "An idea", "--out", str(directory),
             "--constraint", "Must work offline"]), 0)
        with patch.object(rally.Player, "call", side_effect=player), \
                patch.object(rally, "ACTIVE", self.workspace / "active.json"):
            game = rally.play("A note-taking app for field biologists", 3,
                              [rally.Player("mock:left"), rally.Player("mock:right")],
                              directory, rally.Progress())
        self.assertEqual(len(captured), 3)
        for prompt in captured:
            self.assertIn("A note-taking app for field biologists", prompt)
            self.assertIn("Must work offline", prompt)
        owner = [entry for entry in game.state["ledger"] if entry["by"] == "owner"]
        self.assertEqual([entry["status"] for entry in owner], ["standing"])
        self.assertTrue(game.state["disputes"])

    def test_a_brief_without_non_negotiables_runs_with_an_empty_owner_ledger(self):
        directory, _ = self.documented_sequence()
        self.assertFalse((directory / "constraints.md").exists())
        state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
        self.assertEqual([entry for entry in state["ledger"] if entry["by"] == "owner"], [])

    def test_setup_never_overwrites_an_existing_rally_or_its_constraints(self):
        directory, _ = self.documented_sequence("Must work offline")
        before = (directory / "state.json").read_bytes()
        again = self.run_rally("setup", "--out", directory, "--constraint", "Something else")
        self.assertEqual(again.returncode, 1)
        self.assertIn("rally already exists", again.stderr)
        self.assertEqual((directory / "constraints.md").read_text(encoding="utf-8"),
                         "- Must work offline\n")
        self.assertEqual((directory / "state.json").read_bytes(), before)

    def test_setup_refuses_to_reseed_existing_constraints(self):
        directory = self.workspace / "prepared"
        self.assertEqual(rally.setup_command(
            ["--idea", "An idea", "--out", str(directory), "--constraint", "First rule"]), 0)
        self.assertEqual(rally.setup_command(
            ["--idea", "An idea", "--out", str(directory), "--constraint", "Second rule"]), 1)
        self.assertEqual((directory / "constraints.md").read_text(encoding="utf-8"),
                         "- First rule\n")

    def test_a_multiline_constraint_stays_one_bullet(self):
        directory = self.workspace / "multiline"
        self.assertEqual(rally.setup_command(
            ["--out", str(directory), "--constraint", "Keep it\n  offline and free",
             "--constraint", "   ", "--constraint", "Ship in October"]), 0)
        self.assertEqual((directory / "constraints.md").read_text(encoding="utf-8"),
                         "- Keep it offline and free\n- Ship in October\n")
        self.assertEqual([entry["text"] for entry in rally.seed_owner_ledger(directory)],
                         ["Keep it offline and free", "Ship in October"])

    def test_the_skill_documents_the_copyable_sequence(self):
        skill = (SCRIPT.parent.parent / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("rally.py setup", skill)
        self.assertIn("--out", skill)
        self.assertLess(len(skill.splitlines()), 100)


if __name__ == "__main__":
    unittest.main()
