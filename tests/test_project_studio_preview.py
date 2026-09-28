import json
import tempfile
import unittest
from contextlib import chdir
from dataclasses import replace
from pathlib import Path
from unittest import mock

import _test_path
from PIL import Image
from streamlit.testing.v1 import AppTest
from config.chart_config import ChartConfig
from config.dataset_config import DatasetConfig
from core.bar_value_scale import BarValueScaleResolver
from core.rank_celebration import RankCelebrationTimeline
from models.bar_sprite import BarSprite
from studio.package_paths import resolve_project_path
from studio.project_builder import save_project_data
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

    def test_preview_podium_history_ignores_decorative_sprite_changes(self):
        config = ChartConfig(fps=30, steps_per_transition=90, rank_celebration="podium")

        def row(values, *, color, logo_prefix, floating_values=False):
            ordered = sorted(values, key=lambda name: (-values[name], name))
            return tuple(
                BarSprite(name, float(values[name]) if floating_values else values[name],
                          color, 20, 40 + rank * 50, 100, 40,
                          rank=rank + 1, logo_path=f"{logo_prefix}/{name}.png")
                for rank, name in enumerate(ordered)
            )

        initial = {"A": 50, "B": 40, "C": 30}
        promoted = {"B": 55, "A": 50, "C": 30}
        original = (row(initial, color="#112233", logo_prefix="logos"),
                    row(promoted, color="#112233", logo_prefix="logos"))
        styled = (row(initial, color="#AABBCC", logo_prefix="C:/project/logos",
                      floating_values=True),
                  row(promoted, color="#AABBCC", logo_prefix="C:/project/logos",
                      floating_values=True))
        changed_rank = (styled[0], tuple(
            replace(sprite, value=56) if sprite.name == "B" else sprite
            for sprite in styled[1]
        ))
        preview_module._preview_scale_cache.clear()
        preview_module._preview_podium_history_cache.clear()
        original_build = RankCelebrationTimeline._build_events
        builds = []

        def counted_build(timeline):
            builds.append(timeline)
            return original_build(timeline)

        try:
            with mock.patch.object(RankCelebrationTimeline, "_build_events", counted_build):
                preview_module._cached_preview_scale(config, original, original[0], 0, True)
                self.assertEqual(len(builds), 1)
                event = next(iter(preview_module._preview_scale_cache.values()))
                frame = event.rank_celebration_timeline.events[0].frame
                _, celebrations = preview_module._cached_preview_scale(
                    config, styled, styled[1], frame, True,
                )
                self.assertEqual(len(builds), 1)
                self.assertEqual(celebrations[0].anchor_sprite.color, "#AABBCC")
                self.assertTrue(celebrations[0].anchor_sprite.logo_path.startswith("C:/project/"))
                preview_module._cached_preview_scale(
                    config, changed_rank, changed_rank[1], frame, True,
                )
                self.assertEqual(len(builds), 2)
                preview_module._cached_preview_scale(
                    replace(config, steps_per_transition=80), styled, styled[1], frame, True,
                )
                self.assertEqual(len(builds), 3)
        finally:
            preview_module._preview_scale_cache.clear()
            preview_module._preview_podium_history_cache.clear()

    def test_project_studio_style_reruns_reuse_podium_history(self):
        from core.rank_celebration import RankCelebrationTimeline
        from ui import project_studio

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "data").mkdir()
            (root / "logos").mkdir()
            (root / "data" / "sample.csv").write_text(
                "year,name,value\n2020,A,50\n2020,B,40\n"
                "2021,A,50\n2021,B,55\n", encoding="utf-8",
            )
            for name in ("A", "B"):
                Image.new("RGB", (8, 8), "red").save(root / "logos" / f"{name}.png")
            project_data = {
                "name": "ui_podium_preview",
                "chart": {
                    "title": "UI Podium", "layout_preset": "compact_dashboard",
                    "width": 640, "height": 360, "fps": 30,
                    "steps_per_transition": 90, "rank_celebration": "podium",
                    "logos_enabled": True, "logos_dir": "logos",
                    "value_grid_enabled": True,
                },
                "data_source": {"csv_path": "data/sample.csv"},
                "dataset": {
                    "year_column": "year", "name_column": "name",
                    "value_column": "value",
                    "category_logos": {"A": "logos/A.png", "B": "logos/B.png"},
                },
                "fun_facts": {
                    "enabled": False, "layout": "editorial_right",
                    "data_link": "data_pulse",
                },
            }
            project_file = root / "projects" / "ui.json"
            save_project_data(project_data, project_file)
            real_render = preview_module.render_project_preview
            real_build = RankCelebrationTimeline._build_events
            previews = []
            scans = []

            def temporary_preview(project_path, settings, *, project_data=None):
                result = real_render(
                    root / project_path, output_dir=root / "temporary_previews",
                    year=settings["year"], preview_mode=settings["preview_mode"],
                    transition_progress=settings["transition_progress"],
                    force_fun_fact_id=settings.get("force_fun_fact_id"),
                    root_dir=root, project_data=project_data,
                    app_root=project_studio.ROOT_DIR,
                )
                previews.append(Image.open(result).convert("RGBA").tobytes())
                return result

            def counted_build(timeline):
                scans.append(1)
                return real_build(timeline)

            preview_module._preview_scale_cache.clear()
            preview_module._preview_podium_history_cache.clear()
            try:
                with (
                    mock.patch.object(project_studio, "_render_preview", temporary_preview),
                    mock.patch.object(RankCelebrationTimeline, "_build_events", counted_build),
                ):
                    app = AppTest.from_string(
                        "from ui.project_studio import main\nmain()",
                        default_timeout=45,
                    )
                    app.session_state["loaded_project_data"] = project_data
                    app.session_state["loaded_project_path"] = "projects/ui.json"
                    app.session_state[project_studio.ACTIVE_PROJECT_ROOT_STATE] = str(root)
                    app.session_state[project_studio.ACTIVE_PROJECT_KIND_STATE] = "production"
                    app.session_state[project_studio.SAVED_DRAFT_PENDING_STATE] = True
                    app.run()
                    next(x for x in app.button if x.label == "Render preview").click()
                    app.run()
                    self.assertEqual((len(previews), len(scans)), (1, 1))
                    next(x for x in app.segmented_control
                         if x.label == "Editor section").set_value("Canvas")
                    app.run()
                    self.assertEqual(len(scans), 1)
                    before_title = len(previews)
                    next(x for x in app.color_picker
                         if x.label == "Title color").set_value("#A1B2C3")
                    app.run()
                    self.assertEqual(len(previews), before_title + 1)
                    title_frame = previews[-1]
                    next(x for x in app.number_input
                         if x.label == "Title border width").set_value(2.5)
                    app.run()
                    self.assertEqual(len(previews), before_title + 2)
                    border_frame = previews[-1]
                    next(x for x in app.segmented_control
                         if x.label == "Editor section").set_value("Fun facts")
                    app.run()
                    body = next(x for x in app.number_input if x.label == "Body size")
                    body.set_value(body.value + 1)
                    before_body = len(previews)
                    app.run()
                    self.assertEqual(len(previews), before_body + 1)
                    pulse = next(x for x in app.number_input if x.label == "Pulse width")
                    pulse.set_value(pulse.value + 0.5)
                    app.run()
                    self.assertFalse(app.exception)
                    self.assertEqual((len(previews), len(scans)), (before_body + 2, 1))
                    self.assertNotEqual(previews[0], title_frame)
                    self.assertNotEqual(title_frame, border_frame)
                    next(x for x in app.segmented_control
                         if x.label == "Editor section").set_value("Export")
                    app.run()
                    before_irrelevant = len(previews)
                    next(x for x in app.selectbox
                         if x.label == "Frame output mode").set_value("png_sequence")
                    app.run()
                    self.assertEqual((len(previews), len(scans)), (before_irrelevant, 1))
            finally:
                preview_module._preview_scale_cache.clear()
                preview_module._preview_podium_history_cache.clear()

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
