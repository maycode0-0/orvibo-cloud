"""Structural regression tests for the cloud coordinator."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
CONST_PATH = ROOT / "custom_components" / "orvibo_cloud" / "const.py"
COORDINATOR_PATH = ROOT / "custom_components" / "orvibo_cloud" / "coordinator.py"


class CoordinatorStructureTests(unittest.TestCase):
    def test_cloud_state_refreshes_every_minute(self) -> None:
        constants = CONST_PATH.read_text(encoding="utf-8")
        coordinator = COORDINATOR_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=1)",
            constants,
        )
        self.assertIn("update_interval=DEFAULT_SCAN_INTERVAL", coordinator)


if __name__ == "__main__":
    unittest.main()
