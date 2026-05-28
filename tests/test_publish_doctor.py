from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "publish_doctor.py"
SPEC = importlib.util.spec_from_file_location("publish_doctor", MODULE_PATH)
assert SPEC is not None
publish_doctor = importlib.util.module_from_spec(SPEC)
sys.modules["publish_doctor"] = publish_doctor
assert SPEC.loader is not None
SPEC.loader.exec_module(publish_doctor)


class PublishDoctorTest(unittest.TestCase):
    def test_detached_head_is_blocker(self) -> None:
        with (
            patch.object(publish_doctor, "current_branch", return_value=""),
            patch.object(publish_doctor, "current_sha", return_value="abc123"),
        ):
            issues, details = publish_doctor.collect_report(
                base_branch="main",
                skip_fetch=True,
                skip_github=True,
            )

        self.assertIsNone(details["branch"])
        self.assertTrue(any(issue.level == "blocker" and "HEAD detached" in issue.message for issue in issues))

    def test_branch_behind_base_is_blocker(self) -> None:
        with (
            patch.object(publish_doctor, "current_branch", return_value="codex/demo"),
            patch.object(publish_doctor, "current_sha", return_value="abc123"),
            patch.object(publish_doctor, "ref_exists", return_value=True),
            patch.object(publish_doctor, "rev_counts", return_value=(0, 2)),
            patch.object(publish_doctor, "changed_files", return_value=[]),
            patch.object(publish_doctor, "classify", return_value={"changed_count": 0}),
        ):
            issues, details = publish_doctor.collect_report(
                base_branch="main",
                skip_fetch=True,
                skip_github=True,
            )

        self.assertEqual(details["behind"], 2)
        self.assertTrue(any(issue.level == "blocker" and "indietro di 2 commit" in issue.message for issue in issues))

    def test_release_owned_files_block_publish(self) -> None:
        impact = {
            "changed_count": 1,
            "recommended_release_type": "fix",
            "deploy_relevant": False,
            "release_owned": True,
            "release_owned_files": ["CHANGELOG.md"],
        }
        with (
            patch.object(publish_doctor, "current_branch", return_value="codex/demo"),
            patch.object(publish_doctor, "current_sha", return_value="abc123"),
            patch.object(
                publish_doctor,
                "git",
                return_value=subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
            ),
            patch.object(publish_doctor, "ref_exists", return_value=True),
            patch.object(publish_doctor, "rev_counts", return_value=(1, 0)),
            patch.object(publish_doctor, "changed_files", return_value=[]),
            patch.object(publish_doctor, "classify", return_value=impact),
        ):
            issues, details = publish_doctor.collect_report(
                base_branch="main",
                skip_fetch=False,
                skip_github=True,
        )

        self.assertTrue(details["release_owned"])
        self.assertTrue(any(issue.level == "blocker" and "flusso di release" in issue.message for issue in issues))

    def test_main_branch_allows_docs_only_shortcut(self) -> None:
        impact = {
            "changed_count": 1,
            "changed_files": ["docs/LOCAL_DEV.md"],
            "recommended_release_type": "chore",
            "deploy_relevant": False,
            "release_owned": False,
            "docs_only": True,
        }
        with (
            patch.object(publish_doctor, "current_branch", return_value="main"),
            patch.object(publish_doctor, "current_sha", return_value="abc123"),
            patch.object(publish_doctor, "ref_exists", return_value=True),
            patch.object(publish_doctor, "rev_counts", return_value=(0, 0)),
            patch.object(publish_doctor, "changed_files", return_value=[]),
            patch.object(publish_doctor, "classify", return_value=impact),
        ):
            issues, _details = publish_doctor.collect_report(
                base_branch="main",
                skip_fetch=True,
                skip_github=True,
            )

        self.assertFalse([issue for issue in issues if issue.level == "blocker"])
        self.assertTrue(any("docs-only" in issue.message for issue in issues))

    def test_main_branch_blocks_docs_only_outside_direct_allowlist(self) -> None:
        impact = {
            "changed_count": 1,
            "changed_files": [".github/pull_request_template.md"],
            "recommended_release_type": "chore",
            "deploy_relevant": False,
            "release_owned": False,
            "docs_only": True,
        }
        with (
            patch.object(publish_doctor, "current_branch", return_value="main"),
            patch.object(publish_doctor, "current_sha", return_value="abc123"),
            patch.object(publish_doctor, "ref_exists", return_value=True),
            patch.object(publish_doctor, "rev_counts", return_value=(0, 0)),
            patch.object(publish_doctor, "changed_files", return_value=[]),
            patch.object(publish_doctor, "classify", return_value=impact),
        ):
            issues, _details = publish_doctor.collect_report(
                base_branch="main",
                skip_fetch=True,
                skip_github=True,
            )

        self.assertTrue(any(issue.level == "blocker" and "branch dedicata" in issue.message for issue in issues))

    def test_main_branch_blocks_non_docs_changes(self) -> None:
        impact = {
            "changed_count": 1,
            "recommended_release_type": "fix",
            "deploy_relevant": False,
            "release_owned": False,
            "docs_only": False,
        }
        with (
            patch.object(publish_doctor, "current_branch", return_value="main"),
            patch.object(publish_doctor, "current_sha", return_value="abc123"),
            patch.object(publish_doctor, "ref_exists", return_value=True),
            patch.object(publish_doctor, "rev_counts", return_value=(0, 0)),
            patch.object(publish_doctor, "changed_files", return_value=[]),
            patch.object(publish_doctor, "classify", return_value=impact),
        ):
            issues, _details = publish_doctor.collect_report(
                base_branch="main",
                skip_fetch=True,
                skip_github=True,
            )

        self.assertTrue(any(issue.level == "blocker" and "branch dedicata" in issue.message for issue in issues))

    def test_unreadable_failed_runs_block_publish(self) -> None:
        impact = {
            "changed_count": 1,
            "changed_files": ["src/docmolder/bot.py"],
            "recommended_release_type": "fix",
            "deploy_relevant": True,
            "release_owned": False,
            "docs_only": False,
        }
        with (
            patch.object(publish_doctor, "current_branch", return_value="codex/demo"),
            patch.object(publish_doctor, "current_sha", return_value="abc123"),
            patch.object(publish_doctor, "ref_exists", return_value=True),
            patch.object(publish_doctor, "rev_counts", return_value=(1, 0)),
            patch.object(publish_doctor, "changed_files", return_value=[]),
            patch.object(publish_doctor, "classify", return_value=impact),
            patch.object(publish_doctor, "github_available", return_value=True),
            patch.object(
                publish_doctor,
                "gh",
                return_value=subprocess.CompletedProcess(["gh"], 0, stdout="", stderr=""),
            ),
            patch.object(
                publish_doctor,
                "current_failed_runs",
                return_value=subprocess.CompletedProcess(["current_failed_runs.py"], 2, stdout="", stderr="api error"),
            ),
            patch.object(publish_doctor, "open_pr_number", return_value=None),
        ):
            issues, details = publish_doctor.collect_report(
                base_branch="main",
                skip_fetch=True,
                skip_github=False,
            )

        self.assertEqual(details["current_failed_runs_exit"], 2)
        self.assertTrue(any(issue.level == "blocker" and "run GitHub" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
