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
    def _classes(self) -> dict[str, ast.ClassDef]:
        tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))
        return {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        }

    def test_reauth_state_is_not_used_during_first_login(self) -> None:
        flow_class = self._classes()["OrviboCloudConfigFlow"]
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

    def test_config_flow_only_imports_available_home_assistant_constants(self) -> None:
        tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))
        const_import = next(
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "homeassistant.const"
        )
        imported_names = {alias.name for alias in const_import.names}

        self.assertNotIn("CONF_AREA_ID", imported_names)
        self.assertIn("ATTR_AREA_ID", imported_names)

    def test_first_login_requires_device_and_area_steps(self) -> None:
        flow_class = self._classes()["OrviboCloudConfigFlow"]
        methods = {
            node.name: node
            for node in flow_class.body
            if isinstance(node, ast.AsyncFunctionDef)
        }

        self.assertIn("async_step_devices", methods)
        self.assertIn("async_step_area", methods)
        for source_step in ("async_step_user", "async_step_family"):
            called_methods = {
                node.attr
                for node in ast.walk(methods[source_step])
                if isinstance(node, ast.Attribute)
            }
            self.assertIn("async_step_devices", called_methods)

    def test_existing_entries_expose_device_and_area_options(self) -> None:
        options_class = self._classes()["OrviboCloudOptionsFlow"]
        methods = {
            node.name
            for node in options_class.body
            if isinstance(node, ast.AsyncFunctionDef)
        }

        self.assertIn("async_step_init", methods)
        self.assertIn("async_step_devices", methods)
        self.assertIn("async_step_area", methods)


if __name__ == "__main__":
    unittest.main()
