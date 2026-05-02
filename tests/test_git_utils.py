from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.git_utils import (
    ensure_index_lock_available,
    list_index_lock_holders,
    main,
    remove_stale_index_lock,
    resolve_git_dir,
    run_git_command,
    safe_git_main,
)


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

    def test_remove_stale_index_lock_refuses_when_lsof_is_missing(self) -> None:
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
                with self.assertRaisesRegex(RuntimeError, "lsof"):
                    remove_stale_index_lock(str(repo))

            self.assertTrue(lock.exists())

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

    def test_resolve_git_dir_rejects_empty_git_dir_output(self) -> None:
        completed = subprocess.CompletedProcess(["git", "rev-parse", "--git-dir"], 0, stdout="\n", stderr="")
        with patch("docmolder.git_utils.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "Directory git non risolta"):
                resolve_git_dir(".")

    def test_list_index_lock_holders_reports_lsof_failure(self) -> None:
        completed = subprocess.CompletedProcess(["lsof"], 2, stdout="", stderr="permission denied\n")
        with patch("docmolder.git_utils.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                list_index_lock_holders(Path(".git/index.lock"))

    def test_remove_stale_index_lock_refuses_active_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git_dir = repo / ".git"
            git_dir.mkdir()
            (git_dir / "index.lock").write_text("busy", encoding="utf-8")

            def fake_run(args, **kwargs):
                if args[:2] == ["git", "rev-parse"]:
                    return subprocess.CompletedProcess(args, 0, stdout=".git\n", stderr="")
                if args[0] == "lsof":
                    return subprocess.CompletedProcess(args, 0, stdout="COMMAND PID\nvim 123\n", stderr="")
                raise AssertionError(args)

            with patch("docmolder.git_utils.subprocess.run", side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, "ancora in uso"):
                    remove_stale_index_lock(str(repo))

    def test_ensure_index_lock_available_times_out_on_active_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git_dir = repo / ".git"
            git_dir.mkdir()
            (git_dir / "index.lock").write_text("busy", encoding="utf-8")

            def fake_run(args, **kwargs):
                if args[:2] == ["git", "rev-parse"]:
                    return subprocess.CompletedProcess(args, 0, stdout=".git\n", stderr="")
                if args[0] == "lsof":
                    return subprocess.CompletedProcess(args, 0, stdout="COMMAND PID\nvim 123\n", stderr="")
                raise AssertionError(args)

            with patch("docmolder.git_utils.subprocess.run", side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, "Riprova"):
                    ensure_index_lock_available(str(repo), wait_seconds=0)

    def test_main_reports_error_for_failed_lock_removal(self) -> None:
        stderr = io.StringIO()
        with patch("docmolder.git_utils.remove_stale_index_lock", side_effect=RuntimeError("boom")):
            with redirect_stderr(stderr):
                exit_code = main(["."])

        self.assertEqual(exit_code, 1)
        self.assertIn("Errore: boom", stderr.getvalue())

    def test_safe_git_main_requires_command(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = safe_git_main(["--repo", "."])

        self.assertEqual(exit_code, 2)
        self.assertIn("specifica un comando git", stderr.getvalue())

    def test_safe_git_main_prints_stdout_and_success_stderr_to_stdout(self) -> None:
        result = subprocess.CompletedProcess(["git", "status"], 0, stdout="clean\n", stderr="hint\n")
        stdout = io.StringIO()
        with patch("docmolder.git_utils.run_git_command", return_value=result):
            with redirect_stdout(stdout):
                exit_code = safe_git_main(["--repo", ".", "--wait-seconds", "1", "--", "status"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "clean\nhint\n")

    def test_safe_git_main_prints_failing_stderr_to_stderr(self) -> None:
        result = subprocess.CompletedProcess(["git", "bad"], 128, stdout="", stderr="fatal\n")
        stderr = io.StringIO()
        with patch("docmolder.git_utils.run_git_command", return_value=result):
            with redirect_stderr(stderr):
                exit_code = safe_git_main(["bad"])

        self.assertEqual(exit_code, 128)
        self.assertEqual(stderr.getvalue(), "fatal\n")
