import unittest

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


if __name__ == "__main__":
    unittest.main()
