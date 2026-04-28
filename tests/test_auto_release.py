import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from scripts import auto_release


class AutoReleaseTests(unittest.TestCase):
    def test_parse_releasable_conventional_commit(self):
        commit = auto_release.parse_subject(
            "abcdef123456",
            "fix(deploy): keep webhook releases idempotent (#91)",
        )

        self.assertIsNotNone(commit)
        assert commit is not None
        self.assertEqual(commit.type, "fix")
        self.assertEqual(commit.scope, "deploy")
        self.assertEqual(commit.description, "keep webhook releases idempotent")
        self.assertEqual(commit.pr_number, "91")
        self.assertTrue(commit.releasable)

    def test_release_commit_is_ignored(self):
        self.assertIsNone(
            auto_release.parse_subject(
                "abcdef123456",
                "chore(main): release docmolder 0.10.2",
            )
        )

    def test_bump_policy_pre_one(self):
        fix_commit = auto_release.parse_subject("a" * 40, "fix(bot): repair retry flow")
        feat_commit = auto_release.parse_subject("b" * 40, "feat(bot): add retry flow")
        breaking_commit = auto_release.parse_subject("c" * 40, "fix(bot)!: rename retry command")

        assert fix_commit is not None
        assert feat_commit is not None
        assert breaking_commit is not None

        self.assertEqual(auto_release.highest_bump([fix_commit], "0.10.1"), "patch")
        self.assertEqual(auto_release.highest_bump([fix_commit, feat_commit], "0.10.1"), "minor")
        self.assertEqual(auto_release.highest_bump([breaking_commit], "0.10.1"), "minor")

    def test_changelog_entry_groups_commits(self):
        fix_commit = auto_release.parse_subject("a" * 40, "fix(deploy): repair webhook release (#91)")
        feat_commit = auto_release.parse_subject("b" * 40, "feat(bot): add a useful shortcut (#92)")

        assert fix_commit is not None
        assert feat_commit is not None

        plan = auto_release.ReleasePlan(
            current_version="0.10.1",
            next_version="0.11.0",
            previous_tag="docmolder-v0.10.1",
            next_tag="docmolder-v0.11.0",
            commits=[fix_commit, feat_commit],
            changelog_entry="",
        )

        entry = auto_release.build_changelog_entry(plan, "max23468/DocMolder")

        self.assertIn("## [0.11.0]", entry)
        self.assertIn("### Funzionalità", entry)
        self.assertIn("### Correzioni", entry)
        self.assertIn("**bot:** add a useful shortcut", entry)
        self.assertIn("**deploy:** repair webhook release", entry)

    def test_main_uses_separate_git_token_when_configured(self):
        with (
            patch.dict(
                auto_release.os.environ,
                {
                    "DOCMOLDER_RELEASE_GITHUB_TOKEN": "api-token",
                    "DOCMOLDER_RELEASE_GIT_TOKEN": "git-token",
                },
                clear=True,
            ),
            patch.object(auto_release.sys, "argv", ["auto_release.py"]),
            patch.object(auto_release, "apply_release", return_value="ok") as apply_release,
            patch("builtins.print"),
        ):
            exit_code = auto_release.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(apply_release.call_args.kwargs["api_token"], "api-token")
        self.assertEqual(apply_release.call_args.kwargs["git_token"], "git-token")

    def test_main_falls_back_to_api_token_for_git_push(self):
        with (
            patch.dict(auto_release.os.environ, {"DOCMOLDER_RELEASE_GITHUB_TOKEN": "api-token"}, clear=True),
            patch.object(auto_release.sys, "argv", ["auto_release.py"]),
            patch.object(auto_release, "apply_release", return_value="ok") as apply_release,
            patch("builtins.print"),
        ):
            exit_code = auto_release.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(apply_release.call_args.kwargs["api_token"], "api-token")
        self.assertEqual(apply_release.call_args.kwargs["git_token"], "api-token")

    def test_main_loads_tokens_from_secrets_env_file(self):
        with TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / "release.env"
            env_file.write_text(
                "\n".join(
                    [
                        "DOCMOLDER_RELEASE_GITHUB_TOKEN=api-token",
                        "DOCMOLDER_RELEASE_GIT_TOKEN_ENV=DOCMOLDER_RELEASE_CUSTOM_GIT_TOKEN",
                        "DOCMOLDER_RELEASE_CUSTOM_GIT_TOKEN='git-token'",
                        "DOCMOLDER_RELEASE_REPOSITORY=max23468/DocMolder",
                        "IGNORED_TOKEN=not-loaded",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.dict(auto_release.os.environ, {}, clear=True),
                patch.object(auto_release.sys, "argv", ["auto_release.py", "--secrets-env-file", str(env_file)]),
                patch.object(auto_release, "apply_release", return_value="ok") as apply_release,
                patch("builtins.print"),
            ):
                exit_code = auto_release.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(apply_release.call_args.kwargs["api_token"], "api-token")
        self.assertEqual(apply_release.call_args.kwargs["git_token"], "git-token")
        self.assertEqual(apply_release.call_args.kwargs["repository"], "max23468/DocMolder")

    def test_push_with_token_bypasses_local_publish_hooks(self):
        calls: list[list[str]] = []

        def fake_run(args, *, cwd, env=None, capture=True):
            calls.append(args)

        with (
            patch.object(auto_release, "run", side_effect=fake_run),
            patch.object(auto_release, "write_askpass") as write_askpass,
        ):
            tempdir = MagicMock()
            tempdir.__enter__.return_value = "/tmp/release-token"
            tempdir.__exit__.return_value = None
            write_askpass.return_value = tempdir

            auto_release.push_with_token(
                cwd=auto_release.Path("."),
                repository="max23468/DocMolder",
                branch="main",
                tag="docmolder-v0.11.2",
                token="git-token",
            )

        self.assertIn("--no-verify", calls[0])
        self.assertIn("--no-verify", calls[1])


if __name__ == "__main__":
    unittest.main()
