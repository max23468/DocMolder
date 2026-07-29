from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployScriptsTest(unittest.TestCase):
    def test_update_vps_runs_checkout_code_as_application_user(self) -> None:
        script = (ROOT / "deploy" / "update-vps.sh").read_text(encoding="utf-8")

        self.assertIn('sudo -u "${APP_USER}" git reset --hard', script)
        self.assertIn('sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip"', script)
        self.assertIn('sudo -u "${APP_USER}" bash "${APP_DIR}/deploy/smoke-check.sh"', script)
        self.assertNotIn('bash "${APP_DIR}/deploy/install-vps.sh"', script)

    def test_deploy_workflows_only_invoke_root_owned_controller(self) -> None:
        deploy = (ROOT / ".github" / "workflows" / "deploy-vps.yml").read_text(encoding="utf-8")
        rollback = (ROOT / ".github" / "workflows" / "rollback-vps.yml").read_text(encoding="utf-8")

        self.assertIn("/usr/local/sbin/docmolder-update-vps deploy", deploy)
        self.assertIn("/usr/local/sbin/docmolder-update-vps rollback", rollback)
        self.assertNotIn("/opt/docmolder/app/deploy/install-vps.sh", deploy + rollback)
        self.assertNotIn("sudo tar", deploy + rollback)

    def test_rollback_accepts_only_full_sha_from_main_history(self) -> None:
        script = (ROOT / "deploy" / "update-vps.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "rollback-vps.yml").read_text(encoding="utf-8")

        self.assertIn('^[0-9a-f]{40}$', script)
        self.assertIn('git merge-base --is-ancestor "${target_sha}" "${remote_sha}"', script)
        self.assertIn("git rev-parse --verify --end-of-options", workflow)

    def test_systemd_services_do_not_run_checkout_code_as_root(self) -> None:
        services = [
            ROOT / "deploy" / name
            for name in (
                "docmolder.service",
                "docmolder-alertcheck.service",
                "docmolder-db-backup.service",
                "docmolder-github-webhook.service",
                "docmolder-reconcile.service",
            )
        ]
        for service in services:
            text = service.read_text(encoding="utf-8")
            self.assertIn("User=docmolder", text)
            self.assertIn("UMask=0077", text)

    def test_static_site_rejects_symlinked_target_before_cleanup(self) -> None:
        script = (ROOT / "deploy" / "install-static-site.sh").read_text(encoding="utf-8")

        self.assertLess(script.index('realpath -m "${SITE_ROOT}"'), script.index('rm -rf "${SITE_ROOT:?}/"*'))

    def test_all_vps_workflows_require_pinned_host_keys(self) -> None:
        workflows = "".join(
            (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            for name in ("deploy-vps.yml", "rollback-vps.yml", "update-vps-env.yml", "vps-backup.yml", "vps-check.yml")
        )

        self.assertNotIn("accept-new", workflows)
        self.assertEqual(workflows.count("Missing required secret: ${var}"), 5)

    def test_vps_installers_prefer_python_313_without_replacing_system_python(self) -> None:
        install_script = (ROOT / "deploy" / "install-vps.sh").read_text(encoding="utf-8")
        runtime_script = (ROOT / "deploy" / "install-python313.sh").read_text(encoding="utf-8")

        self.assertIn('PYTHON_BIN="${DOCMOLDER_PYTHON_BIN:-}"', install_script)
        self.assertIn("python3.11 python3.11-venv", install_script)
        self.assertIn("python3.11 python3.11-pip", install_script)
        self.assertIn('for candidate in python3.13 python3.12 python3.11 python3', install_script)
        self.assertIn('if [ "${version}" != "${selected_version}" ]; then', install_script)
        self.assertIn('/opt/python/${PYTHON_VERSION}', runtime_script)
        self.assertIn('/usr/local/bin/python3.13', runtime_script)
        self.assertNotIn('/usr/bin/python3.13', runtime_script)

    def test_oracle_setup_installs_python_313_side_by_side_before_creating_venv(self) -> None:
        script = (ROOT / "deploy" / "oracle-setup.sh").read_text(encoding="utf-8")

        self.assertIn('sudo bash "${APP_DIR}/deploy/install-python313.sh"', script)
        self.assertIn('for candidate in python3.13 python3.12 python3.11 python3', script)
        self.assertIn('sudo -u "${APP_USER}" "${PYTHON_BIN}" -m venv "${VENV_DIR}"', script)

    def test_update_vps_env_does_not_interpolate_values_into_sed(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "update-vps-env.yml").read_text(encoding="utf-8")

        self.assertIn("python3 -", workflow)
        self.assertNotIn("sed -i", workflow)
        self.assertNotIn("accept-new", workflow)

    def test_repository_does_not_install_versioned_git_hooks(self) -> None:
        self.assertFalse((ROOT / "githooks" / "pre-commit").exists())
        self.assertFalse((ROOT / "githooks" / "pre-push").exists())
        self.assertFalse((ROOT / "scripts" / "install_git_hooks.sh").exists())
        self.assertNotIn("core.hooksPath", (ROOT / "Makefile").read_text(encoding="utf-8"))

    def test_ci_tooling_is_installed_from_hashed_locks(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        installer = (ROOT / "scripts" / "ci_install.sh").read_text(encoding="utf-8")

        self.assertIn("--require-hashes -r requirements-tools.lock", workflow)
        self.assertIn("--require-hashes -r requirements-dev.lock", installer)
        self.assertIn("--require-hashes -r requirements-build.lock", installer)
        self.assertIn("python -m build --no-isolation", workflow)
        self.assertNotIn("pip install --upgrade pip", installer)

    def test_permission_check_requires_private_runtime_directories(self) -> None:
        script = (ROOT / "deploy" / "check-perms.sh").read_text(encoding="utf-8")

        self.assertIn('check_file_mode "${path}" "700"', script)


if __name__ == "__main__":
    unittest.main()
