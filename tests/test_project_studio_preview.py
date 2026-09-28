import json
import tempfile
import unittest
from contextlib import chdir
from dataclasses import replace
from pathlib import Path
from unittest import mock

import _test_path
from config.chart_config import ChartConfig
from config.dataset_config import DatasetConfig
from core.bar_value_scale import BarValueScaleResolver
from models.bar_sprite import BarSprite
from studio.package_paths import resolve_project_path
from studio import preview as preview_module
from studio.preview import (
    _clamped_progress,
    _resolved_chart_config,
    _resolved_dataset_config,
    _selected_transition_years,
    _selected_year,
    render_project_preview,
)


class ProjectStudioPreviewTest(unittest.TestCase):
    def test_auto_preview_skips_unchanged_and_export_only_edits(self):
        from studio.project_draft import ProjectDraft
        from ui import project_studio

        def draft(**chart):
            return ProjectDraft.create(
                {"chart": {"label_font_size": 24, **chart}},
                "projects/sample.json", {"year": 2000},
            )

        with mock.patch.object(project_studio.st, "session_state", {}):
            initial = draft()
            self.assertFalse(project_studio._should_auto_render_preview(
                initial, enabled=True,
            ))
            self.assertFalse(project_studio._should_auto_render_preview(
                initial, enabled=True,
            ))
            changed = draft(label_font_size=30)
            self.assertTrue(project_studio._should_auto_render_preview(
                changed, enabled=True,
            ))
            self.assertFalse(project_studio._should_auto_render_preview(
                changed, enabled=True,
            ))
            self.assertFalse(project_studio._should_auto_render_preview(
                draft(label_font_size=30, output_file="other.mp4"),
                enabled=True,
            ))

    def test_preview_scale_reuses_history_for_style_but_not_scale_or_sprite_changes(self):
        config = ChartConfig(steps_per_transition=4, rank_celebration="off")
        first = BarSprite("A", 10, "#112233", 100, 100, 200, 30)
        second = BarSprite("A", 20, "#112233", 100, 100, 300, 30)
        history = ((first,), (second,))
        preview_module._preview_scale_cache.clear()
        try:
            with mock.patch.object(
                BarValueScaleResolver, "from_config",
                wraps=BarValueScaleResolver.from_config,
            ) as build:
                initial, _ = preview_module._cached_preview_scale(
                    config, history, history[0], 0, True,
                )
                styled, _ = preview_module._cached_preview_scale(
                    replace(config, title="Changed title"), history,
                    history[0], 0, True,
                )
                self.assertEqual(initial, styled)
                self.assertEqual(build.call_count, 1)

                preview_module._cached_preview_scale(
                    replace(config, leader_full_width_point=0.5),
                    history, history[0], 0, True,
                )
                changed_value = ((replace(first, value=11),), history[1])
                preview_module._cached_preview_scale(
                    config, changed_value, changed_value[0], 0, True,
                )
                changed_color = ((replace(first, color="#AABBCC"),), history[1])
                preview_module._cached_preview_scale(
                    config, changed_color, changed_color[0], 0, True,
                )
                self.assertEqual(build.call_count, 4)
        finally:
            preview_module._preview_scale_cache.clear()

    def test_selects_nearest_year_for_preview(self):
        self.assertEqual(_selected_year(None, [2000, 2005, 2010]), 2000)
        self.assertEqual(_selected_year(2006, [2000, 2005, 2010]), 2005)
        self.assertEqual(_selected_year(2010, [2000, 2005, 2010]), 2010)

    def test_selects_transition_years_for_preview(self):
        self.assertEqual(
            _selected_transition_years(None, [2000, 2005, 2010]),
            (2000, 2005),
        )
        self.assertEqual(
            _selected_transition_years(2005, [2000, 2005, 2010]),
            (2005, 2010),
        )
        self.assertEqual(
            _selected_transition_years(2010, [2000, 2005, 2010]),
            (2005, 2010),
        )

    def test_clamps_preview_progress(self):
        self.assertEqual(_clamped_progress(None), 0.0)
        self.assertEqual(_clamped_progress(-1), 0.0)
        self.assertEqual(_clamped_progress(0.5), 0.5)
        self.assertEqual(_clamped_progress(2), 1.0)

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

    def test_renders_unsaved_project_data_without_writing_project_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            data_dir = root / "data"
            data_dir.mkdir()
            csv_path = data_dir / "sample.csv"
            project_path = root / "projects" / "unsaved.json"
            csv_path.write_text(
                "year,country,value\n"
                "2020,Coal,100\n"
                "2020,Solar,25\n",
                encoding="utf-8",
            )
            project_data = {
                "name": "unsaved_preview",
                "chart": {
                    "title": "Unsaved Preview",
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
                    "csv_path": "data/sample.csv",
                    "source_label_override": "Source: Unsaved",
                },
                "dataset": {
                    "year_column": "year",
                    "name_column": "country",
                    "value_column": "value",
                },
            }

            preview_path = Path(
                render_project_preview(
                    project_path,
                    output_dir="output/preview",
                    year=2020,
                    root_dir=root,
                    project_data=project_data,
                )
            )

            self.assertEqual(
                preview_path,
                root / "output" / "preview" / "preview.png",
            )
            self.assertTrue(preview_path.is_file())
            self.assertFalse(project_path.exists())

    def test_renders_transition_preview_frame_from_project_file(self):
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
                    year=2020,
                    preview_mode="transition",
                    transition_progress=0.5,
                )
            )

            self.assertTrue(preview_path.name.endswith("preview.png"))
            self.assertTrue(preview_path.exists())
            self.assertGreater(preview_path.stat().st_size, 0)

    def test_renders_relative_dataset_independent_of_cwd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            data_dir = root / "data"
            project_dir = root / "projects"
            other_cwd = root / "other"
            data_dir.mkdir()
            project_dir.mkdir()
            other_cwd.mkdir()
            (data_dir / "relative.csv").write_text(
                "year,country,value\n"
                "2020,Coal,100\n"
                "2021,Coal,120\n",
                encoding="utf-8",
            )
            (project_dir / "relative.json").write_text(
                json.dumps(
                    {
                        "name": "relative_preview",
                        "chart": {
                            "width": 320,
                            "height": 180,
                            "dpi": 80,
                            "logos_enabled": False,
                            "max_visible_bars": 1,
                        },
                        "data_source": {
                            "csv_path": "data/relative.csv",
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

            with chdir(other_cwd):
                preview_path = Path(
                    render_project_preview(
                        "projects/relative.json",
                        output_dir="output/preview",
                        year=2021,
                        root_dir=root,
                    )
                )

            expected = root / "output" / "preview" / "preview.png"
            self.assertEqual(preview_path, expected)
            self.assertTrue(preview_path.is_file())

    def test_renderer_assets_use_shared_project_path_resolution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            chart = _resolved_chart_config(
                ChartConfig(
                    background_mode="image",
                    background_image_path="assets/background.png",
                    bar_texture_enabled=True,
                    bar_texture_preset="custom_image",
                    bar_texture_custom_image=r"assets\texture.png",
                    logos_dir="assets/logos",
                ),
                root,
            )
            dataset = _resolved_dataset_config(
                DatasetConfig(
                    category_logos={"A": "assets/logos/a.png"},
                    category_secondary_logos={
                        "A": r"assets\secondary\a.png"
                    },
                ),
                root,
            )

            self.assertEqual(
                chart.background_image_path,
                str(
                    resolve_project_path(
                        "assets/background.png",
                        project_root=root,
                    )
                ),
            )
            self.assertEqual(
                chart.bar_texture_custom_image,
                str(
                    resolve_project_path(
                        r"assets\texture.png",
                        project_root=root,
                    )
                ),
            )
            self.assertEqual(
                chart.logos_dir,
                str(resolve_project_path("assets/logos", project_root=root)),
            )
            self.assertEqual(
                dataset.category_logos["A"],
                str(
                    resolve_project_path(
                        "assets/logos/a.png",
                        project_root=root,
                    )
                ),
            )
            self.assertEqual(
                dataset.category_secondary_logos["A"],
                str(
                    resolve_project_path(
                        r"assets\secondary\a.png",
                        project_root=root,
                    )
                ),
            )


if __name__ == "__main__":
    unittest.main()
