from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=check, capture_output=True, text=True)


class PublishScriptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.origin = self.root / "origin.git"
        self.repo.mkdir()
        run(["git", "init", "-b", "main"], self.repo)
        run(["git", "config", "user.email", "tests@example.invalid"], self.repo)
        run(["git", "config", "user.name", "DocMolder Tests"], self.repo)

        scripts_dir = self.repo / "scripts"
        scripts_dir.mkdir()
        for name in (
            "classify_changes.py",
            "current_failed_runs.py",
            "preflight_publish.sh",
            "publish_change.sh",
            "publish_doctor.py",
        ):
            shutil.copy2(ROOT / "scripts" / name, scripts_dir / name)

        (self.repo / "docs").mkdir()
        (self.repo / "src").mkdir()
        (self.repo / "AGENTS.md").write_text("agents\n", encoding="utf-8")
        (self.repo / "README.md").write_text("readme\n", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
        (self.repo / "docs" / "guide.md").write_text("guide\n", encoding="utf-8")
        (self.repo / "src" / "runtime.py").write_text("print('runtime')\n", encoding="utf-8")
        run(["git", "add", "."], self.repo)
        run(["git", "commit", "-m", "chore: baseline"], self.repo)

        run(["git", "init", "--bare", str(self.origin)], self.root)
        run(["git", "remote", "add", "origin", str(self.origin)], self.repo)
        run(["git", "push", "-u", "origin", "main"], self.repo)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_preflight_allows_staged_docs_only_change_on_main(self) -> None:
        (self.repo / "README.md").write_text("readme\nupdated\n", encoding="utf-8")
        run(["git", "add", "README.md"], self.repo)

        result = run(["bash", "scripts/preflight_publish.sh", "origin/main"], self.repo)

        self.assertIn("publish diretto su main ammesso", result.stdout)
        self.assertIn("Preflight publish OK.", result.stdout)

    def test_preflight_rejects_runtime_to_docs_rename_on_main(self) -> None:
        run(["git", "mv", "src/runtime.py", "docs/runtime.py"], self.repo)

        result = run(["bash", "scripts/preflight_publish.sh", "origin/main"], self.repo, check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Crea una branch dedicata", result.stderr)

    def test_preflight_blocks_staged_pyproject_version_bump(self) -> None:
        run(["git", "switch", "-c", "codex/version-bump"], self.repo)
        (self.repo / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n', encoding="utf-8")
        run(["git", "add", "pyproject.toml"], self.repo)

        result = run(["bash", "scripts/preflight_publish.sh", "origin/main"], self.repo, check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release-please", result.stderr)

    def test_publish_change_pushes_existing_direct_docs_commit(self) -> None:
        (self.repo / "docs" / "guide.md").write_text("guide\nupdated\n", encoding="utf-8")
        run(["git", "add", "docs/guide.md"], self.repo)
        run(["git", "commit", "-m", "chore(docs): update guide"], self.repo)
        before_push = run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()

        result = run(
            ["bash", "scripts/publish_change.sh", "chore(docs): publish pending docs"],
            self.repo,
        )
        origin_main = run(["git", "rev-parse", "origin/main"], self.repo).stdout.strip()

        self.assertEqual(origin_main, before_push)
        self.assertNotIn("Nessun cambio documentale da pubblicare.", result.stdout)


if __name__ == "__main__":
    unittest.main()
