from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    module_path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


check_pr_policy = load_script("check_pr_policy")


class CheckPrPolicyTest(unittest.TestCase):
    def test_accepts_conventional_title_without_release_files(self) -> None:
        errors = check_pr_policy.check_pr_policy(
            title="fix(bot): handle protected PDFs more clearly",
            head_ref="codex/protected-pdfs",
            release_owned=False,
        )

        self.assertEqual(errors, [])

    def test_rejects_non_conventional_title(self) -> None:
        errors = check_pr_policy.check_pr_policy(
            title="Handle protected PDFs",
            head_ref="codex/protected-pdfs",
            release_owned=False,
        )

        self.assertTrue(any("Conventional Commits" in error for error in errors))

    def test_rejects_release_files_in_normal_pr(self) -> None:
        errors = check_pr_policy.check_pr_policy(
            title="fix(bot): handle protected PDFs more clearly",
            head_ref="codex/protected-pdfs",
            release_owned=True,
        )

        self.assertTrue(any("release-owned" in error for error in errors))

    def test_accepts_release_files_on_release_pr(self) -> None:
        errors = check_pr_policy.check_pr_policy(
            title="chore(release): v2.0.7",
            head_ref="codex/release-docmolder-2.0.7",
            release_owned=True,
            release_owned_files=(
                "CHANGELOG.md",
                "pyproject.toml version",
                "src/docmolder/__init__.py",
            ),
            changed_files=("CHANGELOG.md", "pyproject.toml", "src/docmolder/__init__.py"),
        )

        self.assertEqual(errors, [])

    def test_rejects_release_title_on_non_release_branch(self) -> None:
        errors = check_pr_policy.check_pr_policy(
            title="chore(release): v2.0.7",
            head_ref="codex/runtime-fix",
            release_owned=True,
            release_owned_files=("CHANGELOG.md",),
        )

        self.assertTrue(any("branch" in error for error in errors))

    def test_rejects_extra_files_in_release_pr(self) -> None:
        errors = check_pr_policy.check_pr_policy(
            title="chore(release): v2.0.7",
            head_ref="codex/release-docmolder-2.0.7",
            release_owned=True,
            release_owned_files=("CHANGELOG.md", "scripts/check_pr_policy.py"),
            changed_files=("CHANGELOG.md", "scripts/check_pr_policy.py"),
        )

        self.assertTrue(any("file extra" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
