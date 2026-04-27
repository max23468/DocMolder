from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployScriptsTest(unittest.TestCase):
    def test_auto_release_runs_git_work_as_app_user_when_started_by_root(self) -> None:
        script = (ROOT / "deploy" / "auto-release.sh").read_text(encoding="utf-8")

        self.assertIn('APP_USER="${DOCMOLDER_APP_USER:-docmolder}"', script)
        self.assertIn('sudo -E -u "${APP_USER}"', script)

    def test_webhook_install_restarts_listener_after_updating_unit_and_scripts(self) -> None:
        script = (ROOT / "deploy" / "install-github-webhook.sh").read_text(encoding="utf-8")

        self.assertIn("systemctl enable --now docmolder-github-webhook.service", script)
        self.assertIn("systemctl restart docmolder-github-webhook.service", script)


if __name__ == "__main__":
    unittest.main()
