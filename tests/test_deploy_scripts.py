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
        self.assertIn('args+=(--target-version "${DOCMOLDER_RELEASE_TARGET_VERSION}")', script)

    def test_webhook_install_defers_listener_restart_outside_deploy_hook(self) -> None:
        script = (ROOT / "deploy" / "install-github-webhook.sh").read_text(encoding="utf-8")

        self.assertIn('systemctl enable --now "${WEBHOOK_SERVICE}"', script)
        self.assertIn('WEBHOOK_RESTART_MARKER="${DOCMOLDER_GITHUB_WEBHOOK_RESTART_MARKER:-/run/docmolder-github-webhook/restart-requested}"', script)
        self.assertIn('DOCMOLDER_GITHUB_WEBHOOK_IN_WORKER', script)
        self.assertIn('Requested ${WEBHOOK_SERVICE} restart after current webhook job.', script)
        self.assertNotIn("WEBHOOK_RESTART_DELAY", script)

    def test_update_vps_preserves_webhook_worker_restart_env(self) -> None:
        script = (ROOT / "deploy" / "update-vps.sh").read_text(encoding="utf-8")

        self.assertIn('DOCMOLDER_GITHUB_WEBHOOK_IN_WORKER="${DOCMOLDER_GITHUB_WEBHOOK_IN_WORKER:-}"', script)
        self.assertIn('DOCMOLDER_GITHUB_WEBHOOK_RESTART_MARKER="${DOCMOLDER_GITHUB_WEBHOOK_RESTART_MARKER:-}"', script)
        self.assertIn('bash "${APP_DIR}/deploy/install-github-webhook.sh"', script)

    def test_vps_installers_prefer_python_313_without_replacing_system_python(self) -> None:
        install_script = (ROOT / "deploy" / "install-vps.sh").read_text(encoding="utf-8")
        update_script = (ROOT / "deploy" / "update-vps.sh").read_text(encoding="utf-8")
        runtime_script = (ROOT / "deploy" / "install-python313.sh").read_text(encoding="utf-8")

        self.assertIn('PYTHON_BIN="${DOCMOLDER_PYTHON_BIN:-}"', install_script)
        self.assertIn("python3.11 python3.11-venv", install_script)
        self.assertIn("python3.11 python3.11-pip", install_script)
        self.assertIn('for candidate in python3.13 python3.12 python3.11 python3', install_script)
        self.assertIn('if [ "${version}" != "${selected_version}" ]; then', install_script)
        self.assertIn('PYTHON_BIN="${DOCMOLDER_PYTHON_BIN:-}"', update_script)
        self.assertIn('ensure_venv', update_script)
        self.assertIn('sudo systemctl stop "${SERVICE_NAME}" || true', update_script)
        self.assertIn('/opt/python/${PYTHON_VERSION}', runtime_script)
        self.assertIn('/usr/local/bin/python3.13', runtime_script)
        self.assertNotIn('/usr/bin/python3.13', runtime_script)

    def test_oracle_setup_installs_python_313_side_by_side_before_creating_venv(self) -> None:
        script = (ROOT / "deploy" / "oracle-setup.sh").read_text(encoding="utf-8")

        self.assertIn('sudo bash "${APP_DIR}/deploy/install-python313.sh"', script)
        self.assertIn('for candidate in python3.13 python3.12 python3.11 python3', script)
        self.assertIn('sudo -u "${APP_USER}" "${PYTHON_BIN}" -m venv "${VENV_DIR}"', script)


if __name__ == "__main__":
    unittest.main()
