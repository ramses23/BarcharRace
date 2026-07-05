import tempfile
import unittest
from pathlib import Path

import _test_path
from utils.asset_resolver import AssetResolver


class AssetResolverTest(unittest.TestCase):
    def test_resolves_asset_by_normalized_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "United States.png"
            logo_path.write_text("fake image", encoding="utf-8")

            resolver = AssetResolver(temp_dir, extensions=(".png",))

            self.assertEqual(
                resolver.resolve("United States"),
                str(logo_path),
            )

    def test_returns_none_when_asset_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            resolver = AssetResolver(temp_dir, extensions=(".png",))

            self.assertIsNone(resolver.resolve("Mexico"))

    def test_ignores_unsupported_extensions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "USA.svg"
            logo_path.write_text("fake svg", encoding="utf-8")

            resolver = AssetResolver(temp_dir, extensions=(".png",))

            self.assertIsNone(resolver.resolve("USA"))


if __name__ == "__main__":
    unittest.main()
