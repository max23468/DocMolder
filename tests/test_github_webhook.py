from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.github_webhook import (
    GitHubDeployWebhookApp,
    GitHubDeployWebhookHandler,
    GitHubDeployWebhookHTTPServer,
    WebhookConfig,
    build_ref,
    env_int,
    main,
    should_accept_push,
    verify_signature,
)


class GitHubWebhookHelpersTest(unittest.TestCase):
    def _config(
        self,
        deploy_script: str = "/tmp/deploy.sh",
        *,
        secret: str = "secret",
        auto_release_script: str = "/tmp/release.sh",
        restart_marker_path: str = "/tmp/restart-requested",
    ) -> WebhookConfig:
        return WebhookConfig(
            host="127.0.0.1",
            port=8123,
            webhook_path="/webhooks/github/deploy",
            health_path="/webhooks/github/healthz",
            repository="max23468/docmolder",
            branch="main",
            secret=secret,
            deploy_script=deploy_script,
            deploy_timeout_seconds=10,
            auto_release_script=auto_release_script,
            auto_release_timeout_seconds=10,
            max_body_bytes=1024,
            restart_marker_path=restart_marker_path,
            service_name="docmolder-github-webhook.service",
        )

    def test_verify_signature_accepts_matching_payload(self) -> None:
        body = b'{"ref":"refs/heads/main"}'
        secret = "topsecret"
        signature = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        self.assertTrue(verify_signature(secret, body, signature))

    def test_verify_signature_rejects_invalid_signature(self) -> None:
        self.assertFalse(verify_signature("topsecret", b"payload", "sha256=deadbeef"))

    def test_should_accept_push_matches_expected_repo_and_branch(self) -> None:
        payload = {
            "repository": {"full_name": "Max23468/DocMolder"},
            "ref": "refs/heads/main",
            "after": "abc123",
        }

        accepted, target_ref, reason = should_accept_push(payload, "max23468/docmolder", "main")

        self.assertTrue(accepted)
        self.assertEqual(target_ref, "abc123")
        self.assertEqual(reason, "push accepted")

    def test_should_reject_push_for_wrong_repository(self) -> None:
        payload = {
            "repository": {"full_name": "example/other"},
            "ref": "refs/heads/main",
            "after": "abc123",
        }

        accepted, target_ref, reason = should_accept_push(payload, "max23468/docmolder", "main")

        self.assertFalse(accepted)
        self.assertIsNone(target_ref)
        self.assertIn("repository mismatch", reason)

    def test_should_reject_push_for_wrong_branch(self) -> None:
        payload = {
            "repository": {"full_name": "max23468/docmolder"},
            "ref": "refs/heads/develop",
            "after": "abc123",
        }

        accepted, target_ref, reason = should_accept_push(payload, "max23468/docmolder", "main")

        self.assertFalse(accepted)
        self.assertIsNone(target_ref)
        self.assertIn("ref mismatch", reason)

    def test_build_ref_normalizes_branch_name(self) -> None:
        self.assertEqual(build_ref("refs/heads/main"), "refs/heads/main")
        self.assertEqual(build_ref("main"), "refs/heads/main")

    def test_env_int_rejects_invalid_value(self) -> None:
        with patch.dict("docmolder.github_webhook.os.environ", {"DOCMOLDER_BAD_INT": "nope"}):
            with self.assertRaisesRegex(ValueError, "DOCMOLDER_BAD_INT"):
                env_int("DOCMOLDER_BAD_INT", 3)

    def test_should_reject_deleted_push_and_zero_sha(self) -> None:
        deleted_payload = {
            "repository": {"full_name": "max23468/docmolder"},
            "ref": "refs/heads/main",
            "after": "abc123",
            "deleted": True,
        }
        zero_sha_payload = {
            "repository": {"full_name": "max23468/docmolder"},
            "ref": "refs/heads/main",
            "after": "0" * 40,
        }

        self.assertEqual(should_accept_push(deleted_payload, "max23468/docmolder", "main"), (False, None, "branch deleted"))
        self.assertEqual(should_accept_push(zero_sha_payload, "max23468/docmolder", "main"), (False, None, "missing target sha"))

    def test_webhook_config_from_env_normalizes_values_and_ready_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            deploy_script = Path(temp_dir) / "deploy.sh"
            deploy_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            env = {
                "DOCMOLDER_GITHUB_WEBHOOK_HOST": "0.0.0.0",
                "DOCMOLDER_GITHUB_WEBHOOK_PORT": "9000",
                "DOCMOLDER_GITHUB_WEBHOOK_PATH": "",
                "DOCMOLDER_GITHUB_WEBHOOK_HEALTH_PATH": "",
                "DOCMOLDER_GITHUB_WEBHOOK_REPOSITORY": "Max23468/DocMolder",
                "DOCMOLDER_GITHUB_WEBHOOK_BRANCH": "refs/heads/main",
                "DOCMOLDER_GITHUB_WEBHOOK_SECRET": " secret ",
                "DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_SCRIPT": str(deploy_script),
            }

            with patch.dict("docmolder.github_webhook.os.environ", env, clear=True):
                config = WebhookConfig.from_env()
                ready = config.ready

        self.assertEqual(config.port, 9000)
        self.assertEqual(config.repository, "max23468/docmolder")
        self.assertEqual(config.branch, "main")
        self.assertEqual(config.webhook_path, "/webhooks/github/deploy")
        self.assertEqual(config.health_path, "/webhooks/github/healthz")
        self.assertTrue(ready)

    def test_run_deploy_records_success_and_skips_missing_auto_release(self) -> None:
        with TemporaryDirectory() as temp_dir:
            deploy_script = Path(temp_dir) / "deploy.sh"
            deploy_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            app = GitHubDeployWebhookApp(
                self._config(
                    deploy_script=str(deploy_script),
                    auto_release_script=str(Path(temp_dir) / "missing-auto-release.sh"),
                )
            )
            job = self._job()
            completed = MagicMock(returncode=0, stdout="deployed\n", stderr="warn\n")

            with patch("docmolder.github_webhook.subprocess.run", return_value=completed) as run:
                app._run_deploy(job)

        self.assertTrue(app.state.last_result["ok"])
        self.assertEqual(app.state.last_result["delivery_id"], "delivery-1")
        self.assertEqual(app.state.last_result["auto_release"]["reason"], "script missing")
        self.assertFalse(app.state.last_result["webhook_restart"]["requested"])
        self.assertEqual(run.call_args.kwargs["env"]["DOCMOLDER_GITHUB_WEBHOOK_IN_WORKER"], "1")

    def test_run_deploy_records_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            deploy_script = Path(temp_dir) / "deploy.sh"
            deploy_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            app = GitHubDeployWebhookApp(self._config(deploy_script=str(deploy_script)))
            completed = MagicMock(returncode=2, stdout="", stderr="failed\n")

            with patch("docmolder.github_webhook.subprocess.run", return_value=completed):
                with self.assertRaisesRegex(RuntimeError, "Deploy script exited with 2"):
                    app._run_deploy(self._job())

        self.assertEqual(app.state.last_error, "deploy exited with 2")
        self.assertFalse(app.state.last_result["ok"])

    def test_run_auto_release_executes_existing_script(self) -> None:
        with TemporaryDirectory() as temp_dir:
            release_script = Path(temp_dir) / "release.sh"
            release_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            app = GitHubDeployWebhookApp(self._config(auto_release_script=str(release_script)))
            completed = MagicMock(returncode=3, stdout="out\n", stderr="err\n")

            with patch("docmolder.github_webhook.subprocess.run", return_value=completed) as run:
                result = app._run_auto_release()

        self.assertFalse(result["ok"])
        self.assertEqual(result["returncode"], 3)
        self.assertEqual(run.call_args.args[0], [str(release_script)])

    def test_restart_marker_schedules_service_restart_after_job(self) -> None:
        with TemporaryDirectory() as temp_dir:
            marker = Path(temp_dir) / "restart-requested"
            marker.write_text("requested_at=2026-04-28T00:00:00Z\n", encoding="utf-8")
            app = GitHubDeployWebhookApp(
                WebhookConfig(
                    host="127.0.0.1",
                    port=8123,
                    webhook_path="/webhooks/github/deploy",
                    health_path="/webhooks/github/healthz",
                    repository="max23468/docmolder",
                    branch="main",
                    secret="secret",
                    deploy_script="/tmp/deploy.sh",
                    deploy_timeout_seconds=10,
                    auto_release_script="/tmp/release.sh",
                    auto_release_timeout_seconds=10,
                    max_body_bytes=1024,
                    restart_marker_path=str(marker),
                    service_name="docmolder-github-webhook.service",
                )
            )
            completed = MagicMock(returncode=0, stdout="", stderr="")
            with patch("docmolder.github_webhook.subprocess.run", return_value=completed) as run:
                result = app._restart_webhook_if_requested()

        self.assertTrue(result["ok"])
        self.assertTrue(result["requested"])
        self.assertFalse(marker.exists())
        args = run.call_args.args[0]
        self.assertEqual(args[:3], ["systemd-run", "--quiet", "--collect"])
        self.assertIn("--on-active=1s", args)
        self.assertEqual(args[-2:], ["restart", "docmolder-github-webhook.service"])

    def test_webhook_handler_reports_status_and_queues_valid_push(self) -> None:
        with TemporaryDirectory() as temp_dir:
            deploy_script = Path(temp_dir) / "deploy.sh"
            deploy_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            app = GitHubDeployWebhookApp(self._config(deploy_script=str(deploy_script)))
            server = GitHubDeployWebhookHTTPServer(("127.0.0.1", 0), GitHubDeployWebhookHandler, app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status_code, status_payload = self._request(server, "GET", "/webhooks/github/healthz")
                body = json.dumps(
                    {
                        "repository": {"full_name": "Max23468/DocMolder"},
                        "ref": "refs/heads/main",
                        "after": "abc123",
                    }
                ).encode("utf-8")
                headers = {
                    "X-GitHub-Event": "push",
                    "X-GitHub-Delivery": "delivery-1",
                    "X-Hub-Signature-256": self._signature("secret", body),
                    "Content-Type": "application/json",
                }
                push_code, push_payload = self._request(server, "POST", "/webhooks/github/deploy", body, headers)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(status_code, 200)
        self.assertTrue(status_payload["configured"])
        self.assertEqual(push_code, 202)
        self.assertTrue(push_payload["queued"])
        self.assertEqual(push_payload["target_ref"], "abc123")
        self.assertEqual(app.jobs.get_nowait().delivery_id, "delivery-1")

    def test_webhook_handler_rejects_bad_signature_and_ignores_ping(self) -> None:
        with TemporaryDirectory() as temp_dir:
            deploy_script = Path(temp_dir) / "deploy.sh"
            deploy_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            app = GitHubDeployWebhookApp(self._config(deploy_script=str(deploy_script)))
            server = GitHubDeployWebhookHTTPServer(("127.0.0.1", 0), GitHubDeployWebhookHandler, app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                bad_code, bad_payload = self._request(
                    server,
                    "POST",
                    "/webhooks/github/deploy",
                    b"{}",
                    {"X-GitHub-Event": "push", "X-Hub-Signature-256": "sha256=bad"},
                )
                ping_body = b"{}"
                ping_code, ping_payload = self._request(
                    server,
                    "POST",
                    "/webhooks/github/deploy",
                    ping_body,
                    {
                        "X-GitHub-Event": "ping",
                        "X-Hub-Signature-256": self._signature("secret", ping_body),
                    },
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(bad_code, 401)
        self.assertEqual(bad_payload["error"], "invalid signature")
        self.assertEqual(ping_code, 200)
        self.assertEqual(ping_payload["event"], "ping")
        self.assertTrue(app.jobs.empty())

    def test_main_stops_cleanly_after_keyboard_interrupt(self) -> None:
        with patch("docmolder.github_webhook.GitHubDeployWebhookApp.start") as start, patch(
            "docmolder.github_webhook.GitHubDeployWebhookApp.stop"
        ) as stop, patch("docmolder.github_webhook.GitHubDeployWebhookHTTPServer") as server_cls:
            server = server_cls.return_value
            server.serve_forever.side_effect = KeyboardInterrupt

            main(["--secret", "secret", "--deploy-script", "/tmp/missing.sh"])

        start.assert_called_once()
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        stop.assert_called_once()

    def _job(self):
        from docmolder.github_webhook import DeployJob

        return DeployJob(
            delivery_id="delivery-1",
            target_ref="abc123",
            repository="max23468/docmolder",
            branch="main",
            payload={},
        )

    def _signature(self, secret: str, body: bytes) -> str:
        return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    def _request(
        self,
        server: GitHubDeployWebhookHTTPServer,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict]:
        connection = http.client.HTTPConnection(server.server_address[0], server.server_address[1], timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
