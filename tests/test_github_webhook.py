from __future__ import annotations

import hashlib
import hmac
import unittest

from docmolder.github_webhook import build_ref, should_accept_push, verify_signature


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


if __name__ == "__main__":
    unittest.main()
