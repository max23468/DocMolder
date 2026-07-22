from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import os
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(
    command: list[str],
    cwd: Path,
    *,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=check, capture_output=True, text=True, env=env)


class PublishScriptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.origin = self.root / "origin.git"
        self.repo.mkdir()
        run(["git", "init", "-b", "main"], self.repo)
        run(["git", "config", "user.email", "tests@example.invalid"], self.repo)
        run(["git", "config", "user.name", "DocMolder Tests"], self.repo)

        scripts_dir = self.repo / "scripts"
        scripts_dir.mkdir()
        for name in (
            "check_codex_bot_comments.py",
            "classify_changes.py",
            "current_failed_runs.py",
            "generate_pr_body.py",
            "preflight_publish.sh",
            "publish_change.sh",
            "publish_doctor.py",
        ):
            shutil.copy2(ROOT / "scripts" / name, scripts_dir / name)

        (self.repo / "docs").mkdir()
        (self.repo / "src").mkdir()
        (self.repo / "AGENTS.md").write_text("agents\n", encoding="utf-8")
        (self.repo / "README.md").write_text("readme\n", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
        (self.repo / "docs" / "guide.md").write_text("guide\n", encoding="utf-8")
        (self.repo / "src" / "runtime.py").write_text("print('runtime')\n", encoding="utf-8")
        run(["git", "add", "."], self.repo)
        run(["git", "commit", "-m", "chore: baseline"], self.repo)

        run(["git", "init", "--bare", str(self.origin)], self.root)
        run(["git", "remote", "add", "origin", str(self.origin)], self.repo)
        run(["git", "push", "-u", "origin", "main"], self.repo)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_preflight_allows_staged_docs_only_change_on_main(self) -> None:
        (self.repo / "README.md").write_text("readme\nupdated\n", encoding="utf-8")
        run(["git", "add", "README.md"], self.repo)

        result = run(["bash", "scripts/preflight_publish.sh", "origin/main"], self.repo)

        self.assertIn("publish diretto su main ammesso", result.stdout)
        self.assertIn("Preflight publish OK.", result.stdout)

    def test_preflight_rejects_runtime_to_docs_rename_on_main(self) -> None:
        run(["git", "mv", "src/runtime.py", "docs/runtime.py"], self.repo)

        result = run(["bash", "scripts/preflight_publish.sh", "origin/main"], self.repo, check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Crea una branch dedicata", result.stderr)

    def test_preflight_blocks_staged_pyproject_version_bump(self) -> None:
        run(["git", "switch", "-c", "codex/version-bump"], self.repo)
        (self.repo / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n', encoding="utf-8")
        run(["git", "add", "pyproject.toml"], self.repo)

        result = run(["bash", "scripts/preflight_publish.sh", "origin/main"], self.repo, check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("flusso di release", result.stderr)

    def test_classify_skips_dependency_review_for_pyproject_version_only(self) -> None:
        run(["git", "switch", "-c", "codex/release-version"], self.repo)
        (self.repo / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n', encoding="utf-8")

        result = run(
            ["python3", "scripts/classify_changes.py", "--base", "origin/main", "--working-tree", "--format", "json"],
            self.repo,
        )
        report = json.loads(result.stdout)

        self.assertTrue(report["release_owned"])
        self.assertTrue(report["package_build_required"])
        self.assertFalse(report["dependency_review_required"])

    def test_classify_requires_dependency_review_for_pyproject_dependency_change(self) -> None:
        run(["git", "switch", "-c", "codex/dependency"], self.repo)
        (self.repo / "pyproject.toml").write_text(
            '[project]\nversion = "0.1.0"\ndependencies = ["pypdf>=6"]\n',
            encoding="utf-8",
        )

        result = run(
            ["python3", "scripts/classify_changes.py", "--base", "origin/main", "--working-tree", "--format", "json"],
            self.repo,
        )
        report = json.loads(result.stdout)

        self.assertTrue(report["dependency_review_required"])
        self.assertIn("pyproject.toml", report["dependency_files"])

    def test_classify_marks_mixed_release_metadata_and_dependency_changes(self) -> None:
        run(["git", "switch", "-c", "codex/release-with-dependency"], self.repo)
        (self.repo / "pyproject.toml").write_text(
            '[project]\nversion = "0.2.0"\ndependencies = ["pypdf>=6"]\n',
            encoding="utf-8",
        )

        result = run(
            ["python3", "scripts/classify_changes.py", "--base", "origin/main", "--working-tree", "--format", "json"],
            self.repo,
        )
        report = json.loads(result.stdout)

        self.assertIn("pyproject.toml non-version", report["release_owned_files"])

    def test_publish_change_pushes_existing_direct_docs_commit(self) -> None:
        (self.repo / "docs" / "guide.md").write_text("guide\nupdated\n", encoding="utf-8")
        run(["git", "add", "docs/guide.md"], self.repo)
        run(["git", "commit", "-m", "chore(docs): update guide"], self.repo)
        before_push = run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()

        result = run(
            ["bash", "scripts/publish_change.sh", "chore(docs): publish pending docs"],
            self.repo,
        )
        origin_main = run(["git", "rev-parse", "origin/main"], self.repo).stdout.strip()

        self.assertEqual(origin_main, before_push)
        self.assertNotIn("Nessun cambio documentale da pubblicare.", result.stdout)

    def write_fake_gh(self) -> tuple[Path, Path]:
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        log_path = self.root / "gh.log"
        fake_gh = bin_dir / "gh"
        fake_gh.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "${FAKE_GH_LOG}"

case "${1:-}" in
  auth)
    exit 0
    ;;
  run)
    printf '[]\\n'
    exit 0
    ;;
  repo)
    printf 'max23468/DocMolder\\n'
    exit 0
    ;;
  api)
    if [[ "$*" == *"/pulls/"*"/comments"* ]]; then
      printf '[]\\n'
    else
      printf '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[]},"comments":{"nodes":[]}}}}}\\n'
    fi
    exit 0
    ;;
  pr)
    sub="${2:-}"
    case "${sub}" in
      list)
        if [ -f "${FAKE_GH_STATE}" ]; then
          if [[ "$*" == *"length"* ]]; then
            printf '1\\n'
          else
            printf '1\\n'
          fi
        elif [[ "$*" == *"length"* ]]; then
          printf '0\\n'
        fi
        exit 0
        ;;
      create)
        draft=false
        for arg in "$@"; do
          if [ "$arg" = "--draft" ]; then
            draft=true
          fi
        done
        printf 'number=1\\ndraft=%s\\nurl=https://github.example/pr/1\\n' "${draft}" > "${FAKE_GH_STATE}"
        printf 'https://github.example/pr/1\\n'
        exit 0
        ;;
      view)
        if [[ "$*" == *"headRefOid"* ]]; then
          printf '0000000000000000000000000000000000000000\\n'
        elif [[ "$*" == *"isDraft"* ]]; then
          if grep -q '^draft=true$' "${FAKE_GH_STATE}" 2>/dev/null; then
            printf 'true\\n'
          else
            printf 'false\\n'
          fi
        elif [[ "$*" == *"url"* ]]; then
          printf 'https://github.example/pr/1\\n'
        else
          printf '1\\n'
        fi
        exit 0
        ;;
      ready)
        sed -i.bak 's/^draft=true$/draft=false/' "${FAKE_GH_STATE}"
        exit 0
        ;;
      checks|merge)
        exit 0
        ;;
    esac
    ;;
esac

echo "Unhandled gh args: $*" >&2
exit 1
""",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)
        return bin_dir, log_path

    def fake_gh_env(self, bin_dir: Path, log_path: Path) -> dict[str, str]:
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["FAKE_GH_LOG"] = str(log_path)
        env["FAKE_GH_STATE"] = str(self.root / "gh.state")
        return env

    def test_publish_change_creates_ready_pr_by_default(self) -> None:
        run(["git", "switch", "-c", "codex/runtime"], self.repo)
        (self.repo / "src" / "runtime.py").write_text("print('updated')\n", encoding="utf-8")
        bin_dir, log_path = self.write_fake_gh()
        env = self.fake_gh_env(bin_dir, log_path)

        result = run(["bash", "scripts/publish_change.sh", "fix(runtime): update runtime"], self.repo, env=env)
        log = log_path.read_text(encoding="utf-8")

        self.assertIn("PR pronta: https://github.example/pr/1", result.stdout)
        self.assertIn("pr create --base main --head codex/runtime", log)
        self.assertNotIn("pr create --draft", log)
        self.assertNotIn("pr ready", log)
        self.assertNotIn("pr checks", log)
        self.assertNotIn("pr merge", log)

    def test_publish_change_can_create_draft_pr_explicitly(self) -> None:
        run(["git", "switch", "-c", "codex/draft-runtime"], self.repo)
        (self.repo / "src" / "runtime.py").write_text("print('draft')\n", encoding="utf-8")
        bin_dir, log_path = self.write_fake_gh()
        env = self.fake_gh_env(bin_dir, log_path)
        env["DOCMOLDER_PUBLISH_DRAFT"] = "1"

        run(["bash", "scripts/publish_change.sh", "fix(runtime): draft runtime"], self.repo, env=env)
        log = log_path.read_text(encoding="utf-8")

        self.assertIn("pr create --draft --base main --head codex/draft-runtime", log)
        self.assertNotIn("pr ready", log)
        self.assertNotIn("pr checks", log)
        self.assertNotIn("pr merge", log)

    def test_publish_change_can_merge_without_actions_explicitly(self) -> None:
        run(["git", "switch", "-c", "codex/merge-runtime"], self.repo)
        (self.repo / "src" / "runtime.py").write_text("print('merge')\n", encoding="utf-8")
        bin_dir, log_path = self.write_fake_gh()
        env = self.fake_gh_env(bin_dir, log_path)
        env["DOCMOLDER_PUBLISH_MERGE"] = "1"

        result = run(["bash", "scripts/publish_change.sh", "fix(runtime): merge runtime"], self.repo, env=env)
        log = log_path.read_text(encoding="utf-8")

        self.assertIn("PR #1 mergeata.", result.stdout)
        self.assertNotIn("pr checks", log)
        self.assertNotIn("pr merge 1 --auto", log)
        self.assertIn("pr merge 1 --squash --delete-branch --subject fix(runtime): merge runtime (#1)", log)

    def test_publish_change_actions_fallback_keeps_legacy_followup(self) -> None:
        run(["git", "switch", "-c", "codex/actions-runtime"], self.repo)
        (self.repo / "src" / "runtime.py").write_text("print('actions')\n", encoding="utf-8")
        bin_dir, log_path = self.write_fake_gh()
        env = self.fake_gh_env(bin_dir, log_path)
        env["DOCMOLDER_USE_GH_ACTIONS"] = "1"

        run(["bash", "scripts/publish_change.sh", "fix(runtime): actions runtime"], self.repo, env=env)
        log = log_path.read_text(encoding="utf-8")

        self.assertIn("pr create --draft --base main --head codex/actions-runtime", log)
        self.assertIn("pr checks 1 --watch --interval 10", log)
        self.assertIn("pr ready 1", log)
        self.assertIn("pr merge 1 --auto --squash --delete-branch --subject fix(runtime): actions runtime (#1)", log)


if __name__ == "__main__":
    unittest.main()
