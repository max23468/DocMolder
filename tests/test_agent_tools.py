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


agent_parallel_safe = load_script("agent_parallel_safe")
agent_start = load_script("agent_start")
agent_handoff = load_script("agent_handoff")


class AgentToolsTest(unittest.TestCase):
    def test_porcelain_paths_handles_rename(self) -> None:
        output = " M docs/INDEX.md\nR  docs/OLD.md -> docs/NEW.md\n?? scripts/agent_start.py\n"

        self.assertEqual(
            agent_parallel_safe.porcelain_paths(output),
            ["docs/INDEX.md", "docs/NEW.md", "scripts/agent_start.py"],
        )

    def test_recommended_docs_adds_area_specific_docs(self) -> None:
        docs = agent_start.recommended_docs("PDF processing")

        self.assertIn("AGENTS.md", docs)
        self.assertIn("docs/PDF_PIPELINE.md", docs)
        self.assertIn("docs/ARCHITECTURE.md", docs)

    def test_split_items_accepts_repeated_semicolon_values(self) -> None:
        self.assertEqual(
            agent_handoff.split_items(["diff review; targeted tests", "handoff"]),
            ["diff review", "targeted tests", "handoff"],
        )


if __name__ == "__main__":
    unittest.main()
