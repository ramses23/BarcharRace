import json
import tempfile
import unittest
from pathlib import Path

import _test_path
from studio.preview import _selected_year, render_project_preview


class ProjectStudioPreviewTest(unittest.TestCase):
    def test_selects_nearest_year_for_preview(self):
        self.assertEqual(_selected_year(None, [2000, 2005, 2010]), 2000)
        self.assertEqual(_selected_year(2006, [2000, 2005, 2010]), 2005)
        self.assertEqual(_selected_year(2010, [2000, 2005, 2010]), 2010)

    def test_renders_preview_frame_from_project_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "sample.csv"
            project_path = temp_path / "project.json"
            output_dir = temp_path / "preview"

            csv_path.write_text(
                "year,country,value\n"
                "2020,Coal,100\n"
                "2020,Solar,25\n"
                "2021,Coal,120\n"
                "2021,Solar,40\n",
                encoding="utf-8",
            )
            project_path.write_text(
                json.dumps(
                    {
                        "name": "preview_test",
                        "chart": {
                            "title": "Preview Test",
                            "layout_preset": "compact_dashboard",
                            "theme": "clean_report",
                            "typography_preset": "compact",
                            "width": 320,
                            "height": 180,
                            "dpi": 80,
                            "left_margin": 90,
                            "right_margin": 40,
                            "top_margin": 55,
                            "bottom_margin": 30,
                            "bar_height": 16,
                            "bar_gap": 8,
                            "title_font_size": 12,
                            "subtitle_font_size": 8,
                            "time_label_font_size": 30,
                            "source_font_size": 6,
                            "label_font_size": 7,
                            "value_font_size": 7,
                            "title_y": 18,
                            "subtitle_y": 34,
                            "time_label_x": 285,
                            "time_label_y": 145,
                            "source_x": 90,
                            "source_y": 166,
                            "logos_enabled": False,
                            "max_visible_bars": 2,
                        },
                        "selection": {
                            "top_n": 2,
                            "aggregate_other": False,
                        },
                        "data_source": {
                            "source_type": "csv",
                            "csv_path": str(csv_path),
                            "source_label_override": "Source: Preview",
                        },
                        "dataset": {
                            "year_column": "year",
                            "name_column": "country",
                            "value_column": "value",
                        },
                    }
                ),
                encoding="utf-8",
            )

            preview_path = Path(
                render_project_preview(
                    project_path,
                    output_dir=output_dir,
                    year=2021,
                )
            )

            self.assertTrue(preview_path.name.endswith("preview.png"))
            self.assertTrue(preview_path.exists())
            self.assertGreater(preview_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
