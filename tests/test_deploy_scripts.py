from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployScriptsTest(unittest.TestCase):
    def test_auto_release_runs_git_work_as_app_user_when_started_by_root(self) -> None:
        script = (ROOT / "deploy" / "auto-release.sh").read_text(encoding="utf-8")

        self.assertIn('APP_USER="${DOCMOLDER_APP_USER:-docmolder}"', script)
        self.assertIn('preserve_env="DOCMOLDER_RELEASE_GITHUB_TOKEN,DOCMOLDER_RELEASE_GIT_TOKEN,DOCMOLDER_RELEASE_GIT_TOKEN_ENV"', script)
        self.assertIn('preserve_env="${preserve_env},${custom_git_token_env}"', script)
        self.assertIn('sudo --preserve-env="${preserve_env}"', script)
        self.assertIn('--git-token-env "${DOCMOLDER_RELEASE_GIT_TOKEN_ENV:-DOCMOLDER_RELEASE_GIT_TOKEN}"', script)

    def test_webhook_install_defers_listener_restart_outside_deploy_hook(self) -> None:
        script = (ROOT / "deploy" / "install-github-webhook.sh").read_text(encoding="utf-8")

        self.assertIn('systemctl enable --now "${WEBHOOK_SERVICE}"', script)
        self.assertIn("systemd-run", script)
        self.assertIn('--on-active="${WEBHOOK_RESTART_DELAY}"', script)
        self.assertNotIn("sudo systemctl restart docmolder-github-webhook.service", script)


if __name__ == "__main__":
    unittest.main()
