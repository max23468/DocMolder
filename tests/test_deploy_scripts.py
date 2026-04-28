from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployScriptsTest(unittest.TestCase):
    def test_auto_release_runs_git_work_as_app_user_when_started_by_root(self) -> None:
        script = (ROOT / "deploy" / "auto-release.sh").read_text(encoding="utf-8")

        self.assertIn('APP_USER="${DOCMOLDER_APP_USER:-docmolder}"', script)
        self.assertIn('SECRETS_ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/docmolder-auto-release-env.XXXXXX")"', script)
        self.assertIn('chown "${APP_USER}" "${SECRETS_ENV_FILE}"', script)
        self.assertIn('sudo -u "${APP_USER}" "${args[@]}" --secrets-env-file "${SECRETS_ENV_FILE}"', script)
        self.assertNotIn("--preserve-env", script)
        self.assertIn('--git-token-env "${DOCMOLDER_RELEASE_GIT_TOKEN_ENV:-DOCMOLDER_RELEASE_GIT_TOKEN}"', script)

    def test_webhook_install_defers_listener_restart_outside_deploy_hook(self) -> None:
        script = (ROOT / "deploy" / "install-github-webhook.sh").read_text(encoding="utf-8")

        self.assertIn('systemctl enable --now "${WEBHOOK_SERVICE}"', script)
        self.assertIn('WEBHOOK_RESTART_MARKER="${DOCMOLDER_GITHUB_WEBHOOK_RESTART_MARKER:-/run/docmolder-github-webhook/restart-requested}"', script)
        self.assertIn('DOCMOLDER_GITHUB_WEBHOOK_IN_WORKER', script)
        self.assertIn('Requested ${WEBHOOK_SERVICE} restart after current webhook job.', script)
        self.assertNotIn("WEBHOOK_RESTART_DELAY", script)


if __name__ == "__main__":
    unittest.main()
