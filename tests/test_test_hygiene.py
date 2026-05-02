from __future__ import annotations

import importlib.util
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    module_path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


check_test_hygiene = load_script("check_test_hygiene")


class TestHygieneScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "tests").mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_find_hygiene_artifacts_allows_normal_test_files(self) -> None:
        (self.root / "tests" / "test_main.py").write_text("def test_ok(): pass\n", encoding="utf-8")

        self.assertEqual(check_test_hygiene.find_hygiene_artifacts(self.root), [])
        self.assertEqual(check_test_hygiene.main(["--root", str(self.root)]), 0)

    def test_find_hygiene_artifacts_detects_local_copies(self) -> None:
        test_copy = self.root / "tests" / "test_main 2.py"
        coverage_copy = self.root / ".coverage 3"
        test_copy.write_text("def test_duplicate(): pass\n", encoding="utf-8")
        coverage_copy.write_text("coverage data\n", encoding="utf-8")

        self.assertEqual(
            check_test_hygiene.find_hygiene_artifacts(self.root),
            [coverage_copy, test_copy],
        )
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check_test_hygiene.main(["--root", str(self.root)]), 1)


if __name__ == "__main__":
    unittest.main()
