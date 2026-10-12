"""Keep shipped Python scripts on the documented Python 3.9 floor."""
import ast
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'ping-pong' / 'scripts'
FORBIDDEN_BUILTINS = {'aiter', 'anext', 'ExceptionGroup', 'BaseExceptionGroup'}
FORBIDDEN_TYPING = {'Self', 'TypeAlias', 'TypeAliasType', 'Never', 'NotRequired', 'Required', 'TypeGuard'}


class CompatibilityTests(unittest.TestCase):
    def test_python39_scripts(self):
        for path in SCRIPTS.glob('*.py'):
            with self.subTest(script=path.name):
                source = path.read_text(encoding='utf-8')
                tree = ast.parse(source, filename=str(path), feature_version=9)
                annotations = []
                for node in ast.walk(tree):
                    # reject match/case even if a future parser accepts them
                    self.assertNotEqual(type(node).__name__, 'Match', 'match statement')
                    self.assertNotEqual(type(node).__name__, 'match_case', 'match case')
                    if isinstance(node, ast.arg) and node.annotation:
                        annotations.append(node.annotation)
                    if isinstance(node, ast.AnnAssign):
                        annotations.append(node.annotation)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
                        annotations.append(node.returns)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, FORBIDDEN_BUILTINS)
                        if node.func.id == 'zip':
                            self.assertNotIn('strict', [keyword.arg for keyword in node.keywords])
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        names = ([alias.name for alias in node.names]
                                 if isinstance(node, ast.Import) else [node.module or ''])
                        self.assertNotIn('tomllib', names)
                        if isinstance(node, ast.ImportFrom) and node.module == 'typing':
                            imported = {alias.name for alias in node.names}
                            self.assertFalse(FORBIDDEN_TYPING & imported)
                for annotation in annotations:
                    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
                        annotation = ast.parse(annotation.value, mode='eval')
                    self.assertFalse(
                        any(isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
                            for node in ast.walk(annotation)),
                        'Python 3.10 union annotation')

    def test_scripts_have_no_match_keyword_lines(self):
        """CI-friendly grep: bare `match ` statements must not appear in scripts/."""
        for path in SCRIPTS.glob('*.py'):
            with self.subTest(script=path.name):
                for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                    stripped = line.lstrip()
                    if stripped.startswith('#') or stripped.startswith(('"', "'")):
                        continue
                    self.assertFalse(
                        stripped.startswith('match ') and stripped.rstrip().endswith(':'),
                        f'{path.name}:{lineno}: match statement')

    def test_no_unresolved_merge_conflict_markers(self):
        """Several agents merge into these files; a committed marker must fail here.

        docs/evidence/ is a historical record of past runs and is left as captured.
        """
        tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True,
                                 stdout=subprocess.PIPE).stdout.decode()
        for name in filter(None, tracked.split('\0')):
            if name.startswith('docs/evidence/'):
                continue
            path = ROOT / name
            try:
                lines = path.read_text(encoding='utf-8').splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(lines, 1):
                self.assertFalse(
                    line.startswith(('<<<<<<< ', '>>>>>>> ')),
                    f'{name}:{lineno}: unresolved merge conflict marker')


if __name__ == '__main__':
    unittest.main()
