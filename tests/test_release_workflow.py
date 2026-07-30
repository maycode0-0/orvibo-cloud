"""Regression tests for HACS release update notifications."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from typing import Any

import yaml


ROOT = Path(__file__).parents[1]
MANIFEST_PATH = ROOT / "custom_components" / "orvibo_cloud" / "manifest.json"
HACS_PATH = ROOT / "hacs.json"
RELEASE_PATH = ROOT / ".github" / "workflows" / "hacs-release.yml"
VALIDATE_PATH = ROOT / ".github" / "workflows" / "validate.yml"


def _load_workflow(path: Path) -> dict[str, Any]:
    """Parse a GitHub Actions workflow as YAML."""

    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(workflow, dict):
        raise AssertionError(f"Workflow {path.name} must contain a YAML mapping")
    return workflow


class ReleaseWorkflowTests(unittest.TestCase):
    def test_manifest_uses_next_stable_semantic_version(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertEqual(manifest["version"], "0.7.3")
        self.assertRegex(manifest["version"], r"^0\.\d+\.\d+$")

    def test_hacs_uses_release_zip(self) -> None:
        hacs = json.loads(HACS_PATH.read_text(encoding="utf-8"))

        self.assertTrue(hacs["zip_release"])
        self.assertEqual(hacs["filename"], "orvibo_cloud.zip")

    def test_validation_runs_for_push_and_pull_requests(self) -> None:
        workflow = _load_workflow(VALIDATE_PATH)

        self.assertEqual(set(workflow["on"]), {"push", "pull_request"})
        self.assertEqual(
            set(workflow["jobs"]),
            {"unit-tests", "hacs", "hassfest"},
        )
        workflow_text = VALIDATE_PATH.read_text(encoding="utf-8")
        self.assertIn('"PyYAML>=6.0.2"', workflow_text)
        self.assertIn("python -m unittest discover -s tests -v", workflow_text)
        self.assertIn("hacs/action@main", workflow_text)
        self.assertIn("home-assistant/actions/hassfest@master", workflow_text)

    def test_release_has_beta_manual_and_tag_stable_channels(self) -> None:
        workflow = _load_workflow(RELEASE_PATH)
        workflow_text = RELEASE_PATH.read_text(encoding="utf-8")

        self.assertIn('"PyYAML>=6.0.2"', workflow_text)
        self.assertEqual(workflow["on"]["push"]["tags"], ["v*.*.*"])
        self.assertEqual(
            workflow["on"]["schedule"][0]["cron"].split(),
            ["17", "3", "*", "*", "2,5"],
        )
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertEqual(
            set(workflow["jobs"]["release"]["needs"]),
            {"unit-tests", "hacs", "hassfest"},
        )
        release_condition = workflow["jobs"]["release"]["if"]
        self.assertIn("github.event_name == 'schedule'", release_condition)
        self.assertIn("github.event_name == 'workflow_dispatch'", release_condition)
        self.assertIn("github.ref == 'refs/heads/main'", release_condition)
        self.assertIn("github.event_name == 'push'", release_condition)
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", release_condition)

    def test_release_builds_rooted_zip_and_is_idempotent(self) -> None:
        workflow = RELEASE_PATH.read_text(encoding="utf-8")

        self.assertIn("${stable}b${context.runNumber}", workflow)
        self.assertIn("const tagPush = context.eventName === 'push'", workflow)
        self.assertIn("context.ref !== `refs/tags/${stableTag}`", workflow)
        self.assertIn("does not match manifest version", workflow)
        self.assertIn("prerelease ? `v${version}` : stableTag", workflow)
        self.assertIn("cd release-package/orvibo_cloud", workflow)
        self.assertIn("zip -r ../../orvibo_cloud.zip .", workflow)
        self.assertIn("orvibo_cloud.zip", workflow)
        self.assertIn("getReleaseByTag", workflow)
        self.assertIn("uploadReleaseAsset", workflow)
        self.assertIn("assets.some", workflow)
        self.assertIn("Create or repair GitHub release", workflow)
        self.assertIn("content-type", workflow)
        self.assertIn("content-length", workflow)
        self.assertIn("asset.state", workflow)
        self.assertIn("asset.size", workflow)
        self.assertIn("deleteReleaseAsset", workflow)
        self.assertIn("getRef", workflow)
        self.assertIn("does not point to", workflow)
        self.assertNotIn("::set-output", workflow)
        self.assertNotIn("upload-release-asset@v1", workflow)
        self.assertNotIn("create-release@v1", workflow)


if __name__ == "__main__":
    unittest.main()
