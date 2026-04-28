from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


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


codex_dev_report = load_script("codex_dev_report")
github_maintenance_report = load_script("github_maintenance_report")
ops_report = load_script("ops_report")
check_codex_bot_comments = load_script("check_codex_bot_comments")


class CodexReportsTest(unittest.TestCase):
    def test_codex_dev_report_recommends_full_tests_for_runtime(self) -> None:
        report = {
            "fast_static_required": True,
            "full_tests_required": True,
            "package_build_required": False,
            "deploy_relevant": False,
        }

        self.assertIn("make test", codex_dev_report.recommended_checks(report))

    def test_codex_dev_report_flags_release_owned(self) -> None:
        notes = codex_dev_report.risk_notes(
            "codex/demo",
            {"release_owned": True, "release_owned_files": ["CHANGELOG.md"], "changed_count": 1},
        )

        self.assertTrue(any("release-owned" in note for note in notes))

    def test_github_maintenance_report_handles_missing_gh(self) -> None:
        with patch.object(github_maintenance_report, "has_gh", return_value=False):
            report = github_maintenance_report.collect_report(limit=5)

        self.assertFalse(report["ok"])
        self.assertIn("GitHub CLI", report["errors"][0])

    def test_github_maintenance_report_filters_failed_runs_by_current_sha(self) -> None:
        failed_runs = [
            {
                "databaseId": 1,
                "workflowName": "CI",
                "headBranch": "main",
                "headSha": "oldsha",
                "url": "https://example.invalid/old",
            },
            {
                "databaseId": 2,
                "workflowName": "CI",
                "headBranch": "main",
                "headSha": "newsha",
                "url": "https://example.invalid/new",
            },
        ]
        merged_prs = [{"number": 95, "title": "fix deploy", "url": "https://example.invalid/pr/95", "mergedAt": "now"}]

        with (
            patch.object(github_maintenance_report, "has_gh", return_value=True),
            patch.object(github_maintenance_report, "current_branch", return_value="main"),
            patch.object(github_maintenance_report, "current_sha", return_value="newsha"),
            patch.object(github_maintenance_report, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")),
            patch.object(github_maintenance_report, "gh_json", side_effect=[([], None), (failed_runs, None), (merged_prs, None), ([], None)]),
            patch.object(
                github_maintenance_report,
                "codex_bot_comments_for_pr",
                return_value={"ok": True, "has_open_comments": True, "lines": ["open"]},
            ),
        ):
            report = github_maintenance_report.collect_report(limit=5)

        self.assertEqual([item["databaseId"] for item in report["current_branch_failed_runs"]], [2])
        self.assertEqual(report["codex_bot_comment_prs"][0]["number"], 95)

    def test_ops_next_actions_warns_when_health_missing(self) -> None:
        actions = ops_report.next_actions({"health": None})

        self.assertTrue(any("Config/healthcheck" in action for action in actions))

    def test_ops_next_actions_detects_stale_jobs(self) -> None:
        actions = ops_report.next_actions(
            {
                "health": {
                    "alerts": [],
                    "warnings": [],
                    "jobs": {"stale_running_jobs": 2},
                    "backup": {"count": 1},
                    "runtime": {"disk_free_bytes": 90, "disk_total_bytes": 1000},
                }
            }
        )

        self.assertTrue(any("docmolder-reconcile" in action for action in actions))
        self.assertTrue(any("Spazio disco" in action for action in actions))

    def test_resolved_bot_threads_do_not_reappear_from_rest_comments(self) -> None:
        payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": True,
                                    "isOutdated": False,
                                    "path": "src/docmolder/processing.py",
                                    "comments": {
                                        "nodes": [
                                            {
                                                "author": {"login": "chatgpt-codex-connector"},
                                                "body": "resolved",
                                                "url": "https://example.invalid/comment",
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                        "comments": {"nodes": []},
                    }
                }
            }
        }
        rest_comments = [
            {
                "user": {"login": "chatgpt-codex-connector"},
                "body": "resolved",
                "path": "src/docmolder/processing.py",
                "html_url": "https://example.invalid/comment",
                "commit_id": "head",
            }
        ]

        comments = check_codex_bot_comments.find_bot_comments(
            payload,
            rest_comments,
            head_oid="head",
            include_resolved=False,
            include_outdated=False,
        )

        self.assertEqual(comments, [])


if __name__ == "__main__":
    unittest.main()
