"""Regression tests for HACS release update notifications."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
MANIFEST_PATH = ROOT / "custom_components" / "orvibo_cloud" / "manifest.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "hacs-release.yml"


class ReleaseWorkflowTests(unittest.TestCase):
    def test_manifest_uses_stable_semantic_version(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")

    def test_manifest_changes_on_main_publish_hacs_release(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertRegex(workflow, r"branches:\s*\n\s*- main")
        self.assertIn(
            "- custom_components/orvibo_cloud/manifest.json",
            workflow,
        )
        self.assertRegex(workflow, r"permissions:\s*\n\s*contents: write")
        self.assertIn("getReleaseByTag", workflow)
        self.assertIn("createRelease", workflow)
        self.assertLess(
            workflow.index("getReleaseByTag"),
            workflow.index("createRelease"),
        )
        self.assertIn("generate_release_notes: true", workflow)


if __name__ == "__main__":
    unittest.main()
