from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.git_utils import remove_stale_index_lock, run_git_command


class GitUtilsTest(unittest.TestCase):
    def test_remove_stale_index_lock_removes_unheld_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git_dir = repo / ".git"
            git_dir.mkdir()
            lock = git_dir / "index.lock"
            lock.write_text("stale")

            def fake_run(args, **kwargs):
                if args[:2] == ["git", "rev-parse"]:
                    return subprocess.CompletedProcess(args, 0, stdout=".git\n", stderr="")
                if args[0] == "lsof":
                    return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
                raise AssertionError(args)

            with patch("docmolder.git_utils.subprocess.run", side_effect=fake_run):
                message = remove_stale_index_lock(str(repo))

            self.assertFalse(lock.exists())
            self.assertIn("Rimosso lock Git stale", message)

    def test_remove_stale_index_lock_tolerates_missing_lsof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git_dir = repo / ".git"
            git_dir.mkdir()
            lock = git_dir / "index.lock"
            lock.write_text("stale")

            def fake_run(args, **kwargs):
                if args[:2] == ["git", "rev-parse"]:
                    return subprocess.CompletedProcess(args, 0, stdout=".git\n", stderr="")
                if args[0] == "lsof":
                    raise FileNotFoundError("lsof")
                raise AssertionError(args)

            with patch("docmolder.git_utils.subprocess.run", side_effect=fake_run):
                message = remove_stale_index_lock(str(repo))

            self.assertFalse(lock.exists())
            self.assertIn("Rimosso lock Git stale", message)

    def test_run_git_command_waits_for_available_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git_dir = repo / ".git"
            git_dir.mkdir()

            def fake_run(args, **kwargs):
                if args[:2] == ["git", "rev-parse"]:
                    return subprocess.CompletedProcess(args, 0, stdout=".git\n", stderr="")
                if args[:2] == ["git", "status"]:
                    return subprocess.CompletedProcess(args, 0, stdout="clean\n", stderr="")
                raise AssertionError(args)

            with patch("docmolder.git_utils.subprocess.run", side_effect=fake_run):
                result = run_git_command(["status"], repo_path=str(repo))

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "clean\n")
