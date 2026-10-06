"""Keep shipped Python scripts on the documented Python 3.9 floor."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CompatibilityTests(unittest.TestCase):
    def test_python39_scripts(self):
        for path in (ROOT / 'ping-pong' / 'scripts').glob('*.py'):
            with self.subTest(script=path.name):
                tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path), feature_version=9)
                # PEP 604 unions parse as binary operators even under the 3.9 grammar.
                annotations = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.arg) and node.annotation:
                        annotations.append(node.annotation)
                    if isinstance(node, ast.AnnAssign):
                        annotations.append(node.annotation)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
                        annotations.append(node.returns)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, {'aiter', 'anext', 'ExceptionGroup', 'BaseExceptionGroup'})
                        if node.func.id == 'zip':
                            self.assertNotIn('strict', [keyword.arg for keyword in node.keywords])
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or '']
                        self.assertNotIn('tomllib', names)
                        if isinstance(node, ast.ImportFrom) and node.module == 'typing':
                            self.assertFalse({'Self', 'TypeAlias', 'TypeAliasType', 'Never', 'NotRequired', 'Required', 'TypeGuard'} & {alias.name for alias in node.names})
                for annotation in annotations:
                    # Also check postponed/string annotations.
                    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
                        annotation = ast.parse(annotation.value, mode='eval')
                    self.assertFalse(any(isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
                                         for node in ast.walk(annotation)), 'Python 3.10 union annotation')


if __name__ == '__main__':
    unittest.main()
