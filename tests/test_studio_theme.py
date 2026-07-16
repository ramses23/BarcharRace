import tomllib
import unittest
from pathlib import Path


class StudioThemeTest(unittest.TestCase):
    def test_dark_studio_theme_and_upload_limits_are_configured(self):
        root_dir = Path(__file__).resolve().parents[1]
        config_path = root_dir / ".streamlit" / "config.toml"
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))

        theme = config["theme"]
        sidebar = theme["sidebar"]

        self.assertEqual(theme["base"], "dark")
        self.assertEqual(theme["primaryColor"], "#7C5CFC")
        self.assertEqual(theme["backgroundColor"], "#0B0E14")
        self.assertTrue(theme["showWidgetBorder"])
        self.assertTrue(theme["showSidebarBorder"])
        self.assertEqual(sidebar["backgroundColor"], "#080A0F")
        self.assertEqual(config["server"]["maxUploadSize"], 512)
        self.assertEqual(config["server"]["maxMessageSize"], 512)
        self.assertEqual(config["client"]["toolbarMode"], "minimal")


if __name__ == "__main__":
    unittest.main()
