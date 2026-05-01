from __future__ import annotations

import importlib.util
import sys
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
        with patch.object(release_sanity, "latest_docmolder_tag", return_value="docmolder-v1.5.1"):
            self.assertEqual(release_sanity.collect_errors(), [])


if __name__ == "__main__":
    unittest.main()
