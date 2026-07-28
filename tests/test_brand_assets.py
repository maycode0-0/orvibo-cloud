"""Regression tests for HACS and Home Assistant brand assets."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).parents[1]
LOCAL_BRAND_PATH = ROOT / "custom_components" / "orvibo_cloud" / "brand"
LEGACY_BRAND_PATH = ROOT / "brands" / "custom_integrations" / "orvibo_cloud"


class BrandAssetTests(unittest.TestCase):
    def test_hacs_icon_is_a_square_png(self) -> None:
        icon = LOCAL_BRAND_PATH / "icon.png"
        data = icon.read_bytes()

        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual(width, height)
        self.assertGreaterEqual(width,256)

    def test_local_brand_assets_match_legacy_assets(self) -> None:
        expected_assets = {"dark_icon.png", "icon.png", "icon@2x.png", "logo.png"}

        self.assertEqual(
            {path.name for path in LOCAL_BRAND_PATH.glob("*.png")},
            expected_assets,
        )
        for filename in expected_assets:
            local_digest = hashlib.sha256(
                (LOCAL_BRAND_PATH / filename).read_bytes()
            ).digest()
            legacy_digest = hashlib.sha256(
                (LEGACY_BRAND_PATH / filename).read_bytes()
            ).digest()
            self.assertEqual(local_digest, legacy_digest, filename)


if __name__ == "__main__":
    unittest.main()
