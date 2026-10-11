"""Player support is exactly Claude, Codex, Cursor, plus the internal mock (#21).

No provider requests: the CLI binaries and the subprocess layer are both stubbed.
"""
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import sys
import tempfile

from test_rally import rally, SCRIPT


def never_runs(*args, **kwargs):
    raise AssertionError("a provider request was attempted")


class DetectionTests(unittest.TestCase):
    def detect(self, installed, **environment):
        def which(tool):
            return "/usr/bin/" + tool if tool in installed else None

        with patch.object(rally.shutil, "which", side_effect=which), \
                patch.dict(os.environ, environment, clear=False):
            return rally.detect_players()

    def test_only_the_three_supported_clis_are_detected(self):
        self.assertEqual(rally.SUPPORTED_CLIS, ("claude", "codex", "cursor"))
        detected = self.detect({"claude", "codex", "cursor-agent", "gemini",
                                "opencode", "copilot", "aider"})
        self.assertEqual(detected, ["cli:claude", "cli:codex", "cli:cursor"])

    def test_api_keys_do_not_affect_detection_or_selection(self):
        keys = {"ANTHROPIC_API_KEY": "sk-test", "OPENAI_API_KEY": "sk-test",
                "GEMINI_API_KEY": "sk-test", "OPENROUTER_API_KEY": "sk-test"}
        self.assertEqual(self.detect(set(), **keys), [])
        self.assertEqual(rally.auto_pick(self.detect(set(), **keys)), [])
        self.assertEqual(self.detect({"claude"}, **keys), ["cli:claude"])

    def test_cursor_is_found_under_either_binary_name(self):
        self.assertEqual(self.detect({"cursor-agent"}), ["cli:cursor"])
        self.assertEqual(self.detect({"agent"}), ["cli:cursor"])

    def test_default_pair_is_claude_then_codex(self):
        self.assertEqual(rally.auto_pick(["cli:claude", "cli:codex", "cli:cursor"]),
                         ["cli:claude", "cli:codex"])
        self.assertEqual(rally.auto_pick(["cli:cursor", "cli:codex", "cli:claude"]),
                         ["cli:claude", "cli:codex"])

    def test_without_the_default_pair_two_detected_clis_are_used(self):
        self.assertEqual(rally.auto_pick(["cli:claude", "cli:cursor"]),
                         ["cli:claude", "cli:cursor"])

    def test_a_single_cli_is_never_paired_with_itself_or_a_model_alias(self):
        self.assertEqual(rally.auto_pick(["cli:claude"]), ["cli:claude"])
        self.assertEqual(rally.auto_pick([]), [])
        message = rally.missing_players_message(["cli:claude"])
        self.assertIn("Codex", message)
        self.assertIn("--players cli:claude,cli:claude", message)
        self.assertIn("PLAYERS.md", message)
        self.assertNotIn("opus", message)


class SpecTests(unittest.TestCase):
    def test_supported_specs_build_players_with_and_without_a_model(self):
        self.assertEqual(rally.Player("cli:claude").label, "Claude Code")
        self.assertEqual(rally.Player("cli:claude:opus").label, "Claude Code (opus)")
        self.assertEqual(rally.Player("cli:codex:gpt-5").model, "gpt-5")
        self.assertEqual(rally.Player("cli:cursor").tool, "cursor")
        self.assertEqual(rally.Player("mock:left").label, "Mock left")

    def test_two_independent_sessions_of_one_cli_are_allowed(self):
        players = [rally.Player("cli:codex"), rally.Player("cli:codex")]
        self.assertEqual([player.spec for player in players], ["cli:codex", "cli:codex"])

    def test_removed_specs_fail_before_any_provider_request(self):
        removed = ["anthropic:claude-sonnet-5-5", "openai:gpt-5", "gemini:gemini-2.5-pro",
                   "openrouter:openai/gpt-5", "cli:opencode", "cli:copilot",
                   "cli:gemini", "cli:echo", "cli:", "nonsense"]
        with patch.object(rally, "run_cli", side_effect=never_runs):
            for spec in removed:
                with self.subTest(spec=spec):
                    with self.assertRaises(ValueError) as caught:
                        rally.Player(spec)
                    self.assertIn("cli:claude, cli:codex, cli:cursor", str(caught.exception))

    def test_api_transport_helpers_are_gone(self):
        for removed in ("_api", "_post", "API_KINDS", "KEY_ENV", "DEFAULT_MODELS"):
            self.assertFalse(hasattr(rally, removed), removed)
        source = Path(rally.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urllib", source)
        self.assertNotIn("API_KEY", source)


class InvocationTests(unittest.TestCase):
    """Each retained CLI, with and without a model, plus response handling."""

    def call(self, spec, stdout="{}", returncode=0, write_last_message=None):
        recorded = {}

        def fake_run(cmd, stdin, workdir, timeout):
            recorded.update(cmd=cmd, stdin=stdin, workdir=workdir, timeout=timeout)
            if write_last_message is not None:
                Path(workdir, "last.txt").write_text(write_last_message, encoding="utf-8")
            return subprocess.CompletedProcess(cmd, returncode, stdout, "boom")

        with patch.object(rally, "cli_bin", side_effect=lambda tool: "/usr/bin/" + tool), \
                patch.object(rally, "run_cli", side_effect=fake_run):
            answer = rally.Player(spec).call("SYSTEM", "USER")
        return answer, recorded

    def test_claude_invocation(self):
        _, plain = self.call("cli:claude")
        self.assertEqual(plain["cmd"], ["/usr/bin/claude", "-p", "SYSTEM\n\n---\n\nUSER"])
        _, with_model = self.call("cli:claude:opus")
        self.assertEqual(with_model["cmd"][1:3], ["--model", "opus"])

    def test_codex_invocation_reads_its_last_message_file(self):
        answer, recorded = self.call("cli:codex", stdout="log noise",
                                     write_last_message='{"version":"from file"}')
        self.assertEqual(answer, '{"version":"from file"}')
        self.assertEqual(recorded["cmd"][1:4], ["exec", "--skip-git-repo-check",
                                                "--output-last-message"])
        _, with_model = self.call("cli:codex:gpt-5", write_last_message="{}")
        self.assertIn("-m", with_model["cmd"])
        self.assertIn("gpt-5", with_model["cmd"])

    def test_cursor_invocation(self):
        _, plain = self.call("cli:cursor")
        self.assertEqual(plain["cmd"][:7], ["/usr/bin/cursor", "-p", "--trust", "--mode",
                                            "ask", "--output-format", "text"])
        _, with_model = self.call("cli:cursor:gpt-5")
        self.assertIn("--model", with_model["cmd"])

    def test_response_handling_strips_terminal_control_sequences(self):
        answer, _ = self.call("cli:claude", stdout="\x1b[32m{\"version\":\"ok\"}\x1b[0m")
        self.assertEqual(json.loads(answer)["version"], "ok")

    def test_a_failing_cli_reports_the_command_and_its_output(self):
        with self.assertRaises(RuntimeError) as caught:
            self.call("cli:claude", returncode=3)
        self.assertIn("claude exited 3", str(caught.exception))
        self.assertIn("boom", str(caught.exception))

    def test_a_missing_cli_is_reported_without_running_anything(self):
        with patch.object(rally, "cli_bin", return_value=None), \
                patch.object(rally, "run_cli", side_effect=never_runs):
            with self.assertRaises(RuntimeError) as caught:
                rally.Player("cli:codex").call("SYSTEM", "USER")
        self.assertIn("'codex' is not on PATH", str(caught.exception))

    def test_the_cli_timeout_and_its_temp_workdir_are_preserved(self):
        _, recorded = self.call("cli:claude")
        self.assertEqual(recorded["timeout"], 1800)
        self.assertIsNone(recorded["stdin"])
        self.assertIn("pingpong-", recorded["workdir"])
        self.assertFalse(Path(recorded["workdir"]).exists())

    def test_cancellation_removes_the_temp_workdir(self):
        seen = {}

        def interrupted(cmd, stdin, workdir, timeout):
            seen["workdir"] = workdir
            raise KeyboardInterrupt()

        with patch.object(rally, "cli_bin", side_effect=lambda tool: "/usr/bin/" + tool), \
                patch.object(rally, "run_cli", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                rally.Player("cli:claude").call("SYSTEM", "USER")
        self.assertFalse(Path(seen["workdir"]).exists())


class CommandLineTests(unittest.TestCase):
    """The entry point reports a missing CLI instead of substituting a provider."""

    def run_rally(self, *argv):
        with tempfile.TemporaryDirectory() as empty:
            environment = dict(os.environ, PATH=empty, HOME=empty, USERPROFILE=empty,
                               PYTHONDONTWRITEBYTECODE="1")
            for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                        "OPENROUTER_API_KEY"):
                environment["%s" % key] = "sk-should-be-ignored"
            return subprocess.run([sys.executable, str(SCRIPT)] + [str(a) for a in argv],
                                  capture_output=True, text=True, timeout=60,
                                  cwd=empty, env=environment)

    def test_no_supported_cli_reports_the_missing_pair_and_does_not_start(self):
        result = self.run_rally("--idea", "An idea", "-n", 2)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("no supported player CLI", result.stderr)
        self.assertIn("Claude", result.stderr)
        self.assertIn("Codex", result.stderr)
        self.assertIn("PLAYERS.md", result.stderr)
        self.assertNotIn("anthropic:", result.stderr)

    def test_a_removed_spec_is_rejected_before_any_provider_request(self):
        result = self.run_rally("--idea", "An idea", "-n", 2,
                                "--players", "anthropic:claude-sonnet-5-5,cli:claude")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Invalid player spec", result.stderr)
        self.assertIn("cli:claude, cli:codex, cli:cursor", result.stderr)

    def test_list_players_ignores_api_keys(self):
        result = self.run_rally("--list-players")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("detected: nothing", result.stdout)
        self.assertIn("auto pick: none", result.stdout)


if __name__ == "__main__":
    unittest.main()
