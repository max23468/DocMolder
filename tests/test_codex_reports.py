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

    def test_github_maintenance_report_filters_failed_runs(self) -> None:
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
        with (
            patch.object(github_maintenance_report, "has_gh", return_value=True),
            patch.object(github_maintenance_report, "current_branch", return_value="main"),
            patch.object(github_maintenance_report, "current_sha", return_value="newsha"),
            patch.object(github_maintenance_report, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")),
            patch.object(
                github_maintenance_report,
                "gh_json",
                side_effect=[([], None), (failed_runs, None), ([], None)],
            ),
        ):
            report = github_maintenance_report.collect_report(limit=5)

        self.assertEqual([item["databaseId"] for item in report["current_branch_failed_runs"]], [2])

    def test_github_maintenance_report_flags_conventional_releasable_prs(self) -> None:
        open_prs = [
            {"number": 1, "title": "fix(bot): handle retry safely", "labels": []},
            {"number": 2, "title": "chore: update internal notes", "labels": []},
            {"number": 3, "title": "refactor(api)!: rename payload", "labels": []},
            {"number": 4, "title": "chore(main): release docmolder 2.0.5", "labels": []},
        ]

        with (
            patch.object(github_maintenance_report, "has_gh", return_value=True),
            patch.object(github_maintenance_report, "current_branch", return_value="main"),
            patch.object(github_maintenance_report, "current_sha", return_value="sha"),
            patch.object(github_maintenance_report, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")),
            patch.object(
                github_maintenance_report,
                "gh_json",
                side_effect=[(open_prs, None), ([], None), ([], None)],
            ),
        ):
            report = github_maintenance_report.collect_report(limit=5)

        self.assertEqual([item["number"] for item in report["release_prs"]], [1, 3, 4])

    def test_github_maintenance_report_strips_terminal_controls(self) -> None:
        rendered = github_maintenance_report.print_pr(
            {"number": 7, "title": "fix: ok\x1b[2J", "isDraft": False, "url": "https://example.invalid"}
        )

        self.assertNotIn("\x1b", rendered)

    def test_dependabot_major_updates_require_manual_review(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "dependabot-auto-merge.yml").read_text(encoding="utf-8")
        dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

        self.assertIn('UPDATE_TYPE}" = "version-update:semver-major"', workflow)
        self.assertEqual(dependabot.count('          - "major"'), 0)
        self.assertEqual(dependabot.count('          - "minor"'), 2)

    def test_ops_next_actions_warns_when_health_missing(self) -> None:
        actions = ops_report.next_actions({"health": None})

        self.assertTrue(any("Config/healthcheck" in action for action in actions))

    def test_ops_report_fails_when_healthcheck_cannot_execute(self) -> None:
        with (
            patch.object(
                ops_report,
                "collect_report",
                return_value={"ok": False, "health_error": "boom", "services": [], "commands": {}},
            ),
            patch.object(ops_report, "print_text"),
            patch("sys.argv", ["ops_report.py"]),
        ):
            self.assertEqual(ops_report.main(), 1)

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
            [],
            head_oid="head",
            include_resolved=False,
            include_outdated=False,
        )

        self.assertEqual(comments, [])

    def test_clean_codex_reviews_are_not_actionable(self) -> None:
        payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []},
                        "comments": {
                            "nodes": [
                                {
                                    "author": {"login": "chatgpt-codex-connector"},
                                    "body": (
                                        "Codex Review: Didn't find any major issues. Hooray!\n\n"
                                        "**Reviewed commit:** `abcdef0123`"
                                    ),
                                    "url": "https://example.invalid/clean-review",
                                }
                            ]
                        },
                    }
                }
            }
        }

        comments = check_codex_bot_comments.find_bot_comments(
            payload,
            [],
            [],
            head_oid="abcdef0123456789",
            include_resolved=False,
            include_outdated=False,
        )

        self.assertEqual(comments, [])

        comments = check_codex_bot_comments.find_bot_comments(
            payload,
            [],
            [],
            head_oid="fedcba9876543210",
            include_resolved=False,
            include_outdated=False,
        )
        self.assertEqual(comments, [])

        payload["data"]["repository"]["pullRequest"]["comments"]["nodes"][0]["body"] += "\n\n**P2** Correggi."
        comments = check_codex_bot_comments.find_bot_comments(
            payload,
            [],
            [],
            head_oid="abcdef0123456789",
            include_resolved=False,
            include_outdated=False,
        )
        self.assertEqual(len(comments), 1)

    def test_ops_report_uses_env_aware_healthcheck_command(self) -> None:
        with (
            patch.object(ops_report, "load_health", return_value=({"ok": True}, None)),
            patch.object(ops_report, "service_state", return_value={}),
        ):
            report = ops_report.collect_report(check_service=True)

        self.assertEqual(
            report["commands"]["health"],
            "sudo -u docmolder /opt/docmolder/app/deploy/smoke-check.sh 1",
        )

    def test_paginated_rest_pr_comments_cover_graphql_page_limit(self) -> None:
        payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []},
                        "comments": {"nodes": []},
                    }
                }
            }
        }
        rest_pr_comments = [
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "body": "feedback oltre il limite GraphQL",
                "html_url": "https://example.invalid/pr-comment",
            }
        ]

        comments = check_codex_bot_comments.find_bot_comments(
            payload,
            [],
            rest_pr_comments,
            head_oid="head",
            include_resolved=False,
            include_outdated=False,
        )

        self.assertEqual([comment.source for comment in comments], ["rest-pr-comment"])

    def test_paginated_rest_comments_slurp_and_flatten_pages(self) -> None:
        completed = SimpleNamespace(
            returncode=0,
            stdout='[[{"id": 1}], [{"id": 2}]]',
            stderr="",
        )
        with patch.object(check_codex_bot_comments, "run", return_value=completed) as run:
            comments = check_codex_bot_comments.load_paginated_rest_comments(
                "repos/owner/repo/issues/1/comments",
                error_message="failed",
            )

        self.assertEqual(comments, [{"id": 1}, {"id": 2}])
        self.assertIn("--slurp", run.call_args.args[0])

    def test_check_codex_bot_comments_reports_repo_lookup_failures_as_errors(self) -> None:
        with (
            patch.object(check_codex_bot_comments.shutil, "which", return_value="/usr/bin/gh"),
            patch.object(check_codex_bot_comments, "current_pr_number", return_value=63),
            patch.object(check_codex_bot_comments, "repo_owner_name", side_effect=RuntimeError("gh unavailable")),
            patch("sys.argv", ["check_codex_bot_comments.py", "--fail"]),
        ):
            self.assertEqual(check_codex_bot_comments.main(), 2)


if __name__ == "__main__":
    unittest.main()
