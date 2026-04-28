from __future__ import annotations

import hashlib
import hmac
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.github_webhook import GitHubDeployWebhookApp, WebhookConfig, build_ref, should_accept_push, verify_signature


class GitHubWebhookHelpersTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
