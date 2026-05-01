from __future__ import annotations

import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


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


release_sanity = load_script("release_sanity")


class ReleaseSanityTest(unittest.TestCase):
    def test_current_release_metadata_is_aligned(self) -> None:
        manifest = release_sanity.read_json(ROOT / ".release-please-manifest.json")
        self.assertIsInstance(manifest, dict)
        manifest_version = manifest.get(".")
        self.assertIsInstance(manifest_version, str)

        expected_tag = f"docmolder-v{manifest_version}"
        with patch.object(release_sanity, "latest_docmolder_tag", return_value=expected_tag):
            self.assertEqual(release_sanity.collect_errors(), [])

    def test_detects_stale_top_changelog_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src" / "docmolder").mkdir(parents=True)
            (root / ".release-please-manifest.json").write_text('{"." : "1.5.1"}', encoding="utf-8")
            (root / "pyproject.toml").write_text('[project]\nversion = "1.5.1"\n', encoding="utf-8")
            (root / "src" / "docmolder" / "__init__.py").write_text('__version__ = "1.5.1"\n', encoding="utf-8")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [1.5.0]\n\n## [1.5.1]\n",
                encoding="utf-8",
            )
            (root / "release-please-config.json").write_text(
                textwrap.dedent(
                    """
                    {
                      "packages": {
                        ".": {
                          "release-type": "python",
                          "package-name": "docmolder",
                          "changelog-path": "CHANGELOG.md",
                          "include-v-in-tag": true,
                          "extra-files": ["src/docmolder/__init__.py"],
                          "changelog-sections": [
                            {"type": "feat", "section": "Funzionalità"},
                            {"type": "fix", "section": "Correzioni"},
                            {"type": "deps", "section": "Dipendenze"},
                            {"type": "ci", "section": "Interno", "hidden": true},
                            {"type": "test", "section": "Interno", "hidden": true},
                            {"type": "chore", "section": "Interno", "hidden": true},
                            {"type": "refactor", "section": "Interno", "hidden": true},
                            {"type": "build", "section": "Interno", "hidden": true}
                          ]
                        }
                      }
                    }
                    """
                ),
                encoding="utf-8",
            )

            with (
                patch.object(release_sanity, "ROOT", root),
                patch.object(release_sanity, "latest_docmolder_tag", return_value="docmolder-v1.5.1"),
            ):
                errors = release_sanity.collect_errors()

        self.assertIn("Prima sezione CHANGELOG.md 1.5.0, attesa 1.5.1.", errors)


if __name__ == "__main__":
    unittest.main()
