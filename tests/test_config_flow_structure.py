"""Structural regression tests for the Home Assistant config flow."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

CONFIG_FLOW = (
    Path(__file__).parents[1]
    / "custom_components"
    / "orvibo_cloud"
    / "config_flow.py"
)


class ConfigFlowStructureTests(unittest.TestCase):
    def test_reauth_state_is_not_used_during_first_login(self) -> None:
        tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))
        flow_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "OrviboCloudConfigFlow"
        )
        methods = {
            node.name: node
            for node in flow_class.body
            if isinstance(node, ast.AsyncFunctionDef)
        }

        user_names = {
            node.attr
            for node in ast.walk(methods["async_step_user"])
            if isinstance(node, ast.Attribute)
        }
        reauth_names = {
            node.attr
            for node in ast.walk(methods["async_step_reauth_confirm"])
            if isinstance(node, ast.Attribute)
        }

        self.assertNotIn("_reauth_entry", user_names)
        self.assertIn("_reauth_entry", reauth_names)


if __name__ == "__main__":
    unittest.main()
