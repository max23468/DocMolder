from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
