import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import _test_path
from PIL import Image, ImageDraw

from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.fun_fact_config import FunFactConfig
from core.layout_engine import LayoutEngine
from core.scene_geometry import build_scene_geometry
from core.bar_value_scale import BarValueScaleResolver, scale_bar_sprites
from core.value_axis import ValueAxisTracker
from core.motion_engine import MotionEngine
from core.rank_motion import (
    RANK_MOTION_HEIGHT_EMPHASIS,
    ordered_rank_motion_sprites,
    rank_motion_depth,
    rank_motion_effective_height,
    visual_rank_motion_sprite,
)
from models.bar_data import BarData
from models.bar_sprite import BarSprite
from models.scene import Scene
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from studio.project_builder import build_project_data, project_form_values
from config.project_file_loader import load_project_data
from studio.preview import render_project_preview
from studio.project_runtime import resolve_project_preset_paths
from utils.logo_color import representative_logo_color


def sprite(name, rank, y):
    return BarSprite(
        name=name, value=100, color="#123456", x=40, y=y,
        width=100, height=20, rank=rank,
    )


class MotionStyleUpgradeTest(unittest.TestCase):

    def test_font_variants_and_fallback_are_resolved_to_real_files(self):
        renderer = BarRenderer(config=ChartConfig())
        try:
            variants = {
                renderer._text_font_path("DejaVu Sans", weight, style)
                for weight in ("normal", "bold")
                for style in ("normal", "italic")
            }
            fallback = renderer._text_font_path(
                "Definitely Missing Font", "bold", "italic"
            )
        finally:
            renderer.close()
        self.assertTrue(all(Path(path).is_file() for path in variants))
        self.assertTrue(Path(fallback).is_file())
        self.assertGreaterEqual(len(variants), 3)

    def test_typography_styles_survive_builder_and_loader(self):
        data = self._project_data(
            text_styles={
                "title_font_weight": "bold",
                "title_font_style": "italic",
                "label_font_weight": "bold",
                "label_font_style": "italic",
            },
            bar_gap=44,
            bar_color_source="primary_logo",
            primary_logo_min_size=36,
            background_motion="forward_motion",
            background_motion_speed=1.8,
            background_motion_intensity=0.6,
            fun_facts={
                "editorial_headline_font_weight": "bold",
                "editorial_headline_font_style": "italic",
            },
        )
        config = load_project_data(data).chart_config
        self.assertEqual((config.title_font_weight, config.title_font_style), ("bold", "italic"))
        self.assertEqual((config.label_font_weight, config.label_font_style), ("bold", "italic"))
        self.assertEqual(config.bar_gap, 44)
        self.assertEqual(config.bar_color_source, "primary_logo")
        self.assertEqual(config.primary_logo_min_size, 36)
        self.assertEqual(config.background_motion, "forward_motion")
        self.assertEqual(config.background_motion_speed, 1.8)
        facts = load_project_data(data).fun_fact_config
        self.assertEqual(facts.editorial_headline_font_style, "italic")

    def test_bar_spacing_default_and_increased_geometry(self):
        bars = [BarData("A", 10), BarData("B", 9)]
        legacy = LayoutEngine(ChartConfig(logos_enabled=False)).build(bars)
        spaced = LayoutEngine(ChartConfig(logos_enabled=False, bar_gap=50)).build(bars)
        self.assertEqual(legacy[1].y - legacy[0].y, 54 + 18)
        self.assertEqual(spaced[1].y - spaced[0].y, 54 + 50)
        self.assertGreater(
            spaced[1].y - spaced[0].y,
            (spaced[0].height + spaced[1].height) / 2,
        )

    def test_logo_color_ignores_transparency_and_white_padding(self):
        with tempfile.TemporaryDirectory() as directory:
            red = Path(directory) / "red.png"
            blue = Path(directory) / "blue.jpg"
            padded = Path(directory) / "padded.png"
            Image.new("RGBA", (32, 32), (240, 20, 20, 255)).save(red)
            Image.new("RGB", (32, 32), (15, 45, 230)).save(blue)
            image = Image.new("RGBA", (80, 80), (255, 255, 255, 0))
            ImageDraw.Draw(image).rectangle((31, 31, 48, 48), fill=(235, 25, 25, 255))
            image.save(padded)
            self.assertGreater(int(representative_logo_color(red)[1:3], 16), 180)
            self.assertGreater(int(representative_logo_color(blue)[5:7], 16), 170)
            self.assertGreater(int(representative_logo_color(padded)[1:3], 16), 180)

    def test_logo_color_source_falls_back_and_preserves_manual_color(self):
        with tempfile.TemporaryDirectory() as directory:
            logo = Path(directory) / "logo.png"
            Image.new("RGBA", (24, 24), (20, 210, 60, 255)).save(logo)
            bar = BarData("A", 10, color="#AA1122", logo_path=str(logo))
            manual = LayoutEngine(ChartConfig(logos_enabled=True)).build([bar])[0]
            automatic = LayoutEngine(ChartConfig(
                logos_enabled=True, bar_color_source="primary_logo"
            )).build([bar])[0]
            restored = LayoutEngine(ChartConfig(logos_enabled=True)).build([bar])[0]
            missing = LayoutEngine(ChartConfig(
                logos_enabled=True, bar_color_source="primary_logo"
            )).build([replace(bar, logo_path=str(Path(directory) / "missing.png"))])[0]
            self.assertEqual(manual.color, "#AA1122")
            self.assertNotEqual(automatic.color, manual.color)
            self.assertEqual(restored.color, "#AA1122")
            self.assertEqual(missing.color, "#AA1122")

    def test_forward_background_is_frame_deterministic_and_off_is_legacy(self):
        self.assertEqual(ChartConfig().background_motion, "off")
        renderer = BarRenderer(config=ChartConfig(
            width=320, height=180, dpi=72,
            background_motion="forward_motion",
        ))
        try:
            first = renderer._forward_motion_background(100)
            repeated = renderer._forward_motion_background(100)
            later = renderer._forward_motion_background(110)
        finally:
            renderer.close()
        self.assertTrue((first == repeated).all())
        self.assertFalse((first == later).all())

    def test_rank_y_uses_period_endpoints_without_changing_steps(self):
        animation = AnimationConfig(easing="ease_in_out_cubic")
        engine = MotionEngine(animation)
        start = [sprite("A", 2, 40), sprite("B", 3, 70), sprite("C", 5, 130)]
        end = [sprite("A", 3, 70), sprite("B", 2, 40), sprite("C", 2, 40)]
        configured_steps = 8
        frames = engine.interpolate_sprites_continuous(
            start, start, end, end, steps=configured_steps
        )
        midpoint = {item.name: item for item in frames[configured_steps // 2]}
        eased = animation.easing_function()(0.5)
        self.assertAlmostEqual(midpoint["A"].y, 40 + (30 * eased))
        self.assertAlmostEqual(midpoint["B"].y, 70 - (30 * eased))
        self.assertAlmostEqual(midpoint["C"].y, 130 - (90 * eased))
        self.assertEqual(len(frames), configured_steps + 1)

    def test_rank_motion_two_bar_swap_depth_and_thickness(self):
        engine = MotionEngine(AnimationConfig(easing="ease_out_cubic"))
        start = [sprite("A", 1, 40), sprite("B", 2, 80)]
        end = [sprite("A", 2, 80), sprite("B", 1, 40)]
        frames = engine.interpolate_sprites(start, end, steps=5)

        for frame in frames:
            self.assertEqual([item.name for item in frame], ["A", "B"])
            self.assertEqual(frame[0].rank_motion_state, "falling")
            self.assertEqual(frame[1].rank_motion_state, "rising")
            self.assertLess(rank_motion_depth(frame[0]), rank_motion_depth(frame[1]))

        midpoint = {item.name: item for item in frames[2]}
        self.assertEqual(rank_motion_effective_height(midpoint["A"]), 16)
        self.assertEqual(rank_motion_effective_height(midpoint["B"]), 24)
        self.assertEqual(
            visual_rank_motion_sprite(midpoint["A"]).y,
            midpoint["A"].y,
        )
        self.assertEqual(
            visual_rank_motion_sprite(midpoint["B"]).y,
            midpoint["B"].y,
        )
        for endpoint in (frames[0], frames[-1]):
            self.assertTrue(all(
                rank_motion_effective_height(item) == item.height
                for item in endpoint
            ))

    def test_rank_motion_multi_bar_ties_and_top_n_entry_exit_are_stable(self):
        start = [
            sprite("A", 1, 20),
            sprite("B", 2, 40),
            sprite("C", 3, 60),
            sprite("D", 4, 80),
        ]
        end = [
            sprite("A", 4, 80),
            sprite("B", 1, 20),
            sprite("C", 2, 40),
            sprite("D", 3, 60),
        ]
        frames = MotionEngine().interpolate_sprites(start, end, steps=7)
        for frame in frames:
            self.assertEqual([item.name for item in frame], ["A", "B", "C", "D"])
            self.assertEqual(
                [item.rank_motion_state for item in frame],
                ["falling", "rising", "rising", "rising"],
            )

        tied = [
            replace(frames[3][2], name="Zulu", rank_motion_target=2),
            replace(frames[3][2], name="Alpha", rank_motion_target=2),
        ]
        self.assertEqual(
            [item.name for item in ordered_rank_motion_sprites(tied)],
            ["Alpha", "Zulu"],
        )

        entry_exit = MotionEngine().interpolate_sprites(
            [sprite("Exit", 1, 20)],
            [sprite("Enter", 1, 20)],
            steps=3,
        )
        states = {
            item.name: item.rank_motion_state
            for item in entry_exit[1]
        }
        self.assertEqual(states, {"Exit": "falling", "Enter": "rising"})
        opacities = {item.name: item.opacity for item in entry_exit[1]}
        self.assertGreater(opacities["Exit"], 0)
        self.assertGreater(opacities["Enter"], 0)

    def test_rank_motion_reversal_stable_and_small_height_safety(self):
        engine = MotionEngine()
        first = engine.interpolate_sprites(
            [sprite("A", 3, 60)],
            [sprite("A", 1, 20)],
            steps=3,
        )
        second = engine.interpolate_sprites(
            [sprite("A", 1, 20)],
            [sprite("A", 2, 40)],
            steps=3,
        )
        self.assertEqual(first[1][0].rank_motion_state, "rising")
        self.assertEqual(second[1][0].rank_motion_state, "falling")
        self.assertEqual(rank_motion_effective_height(first[-1][0]), 20)
        self.assertEqual(rank_motion_effective_height(second[0][0]), 20)

        stable = replace(
            sprite("Stable", 1, 20),
            rank_motion_state="stable",
            rank_motion_progress=0.5,
        )
        tiny = replace(
            sprite("Tiny", 2, 40),
            height=2,
            rank_motion_state="falling",
            rank_motion_progress=0.5,
        )
        zero = replace(tiny, height=0, rank_motion_progress=0)
        self.assertEqual(rank_motion_effective_height(stable), stable.height)
        self.assertGreater(rank_motion_effective_height(tiny), 0)
        self.assertGreater(rank_motion_effective_height(zero), 0)

    def test_rank_motion_render_paths_borders_tracks_and_nominal_geometry(self):
        falling = replace(
            sprite("Falling", 2, 90),
            color="#FF0000",
            width=160,
            rank_motion_state="falling",
            rank_motion_progress=0.5,
            rank_motion_target=2,
        )
        rising = replace(
            sprite("Rising", 1, 90),
            color="#0000FF",
            width=160,
            rank_motion_state="rising",
            rank_motion_progress=0.5,
            rank_motion_target=1,
        )
        self.assertEqual(RANK_MOTION_HEIGHT_EMPHASIS, 4)

        modes = {
            "solid": dict(
                bar_appearance_mode="simple",
                bar_gradient_enabled=False,
            ),
            "gradient": dict(
                bar_appearance_mode="unified",
                bar_fill_type="gradient",
                bar_gradient_direction="horizontal",
                bar_gradient_color_count=2,
                bar_fill_use_category_color=True,
                bar_edge_darkening=0,
            ),
            "material": dict(
                bar_appearance_mode="advanced",
                bar_fill_type="gradient",
                bar_track_enabled=True,
                bar_track_opacity=0.25,
            ),
        }
        for width, height in ((320, 180), (180, 320)):
            for mode, options in modes.items():
                with self.subTest(width=width, height=height, mode=mode):
                    renderer = BarRenderer(config=ChartConfig(
                        width=width,
                        height=height,
                        dpi=72,
                        left_margin=20,
                        right_margin=20,
                        title_enabled=False,
                        subtitle_enabled=False,
                        source_label_enabled=False,
                        time_label_enabled=False,
                        category_labels_enabled=False,
                        value_labels_enabled=False,
                        rank_labels_enabled=False,
                        logos_enabled=False,
                        bar_shadow_enabled=False,
                        bar_border_enabled=True,
                        bar_shape="rounded",
                        **options,
                    ))
                    scene = Scene(title="", bars=[rising, falling])
                    try:
                        rgba = renderer.render_rgba(scene)
                        self.assertEqual(len(rgba), width * height * 4)
                        if mode == "material":
                            track_heights = [
                                path.get_extents().height
                                for path in renderer._advanced_track_collection.get_paths()
                            ]
                            body_heights = [
                                command[0].shape[0]
                                for command in renderer._advanced_composite_artist.commands
                            ]
                            self.assertEqual(track_heights, [20, 20])
                            self.assertEqual(body_heights, [16, 24])
                            body_colors = []
                            for command in renderer._advanced_composite_artist.commands:
                                pixels = command[0]
                                visible = pixels[:, :, 3] > 0
                                body_colors.append(
                                    pixels[:, :, :3][visible].mean(axis=0)
                                )
                            self.assertGreater(body_colors[0][0], body_colors[0][2])
                            self.assertGreater(body_colors[1][2], body_colors[1][0])
                        else:
                            border_heights = [
                                artists.border.get_path().get_extents().height
                                for artists in renderer._bar_artists[:2]
                            ]
                            self.assertEqual(border_heights, [16, 24])
                            if mode == "gradient":
                                colors = renderer._gradient_artist.get_facecolors()
                                self.assertGreater(colors[0][0], colors[0][2])
                                self.assertGreater(colors[-1][2], colors[-1][0])
                            else:
                                colors = [
                                    artists.bar.get_facecolor()
                                    for artists in renderer._bar_artists[:2]
                                ]
                                self.assertGreater(colors[0][0], colors[0][2])
                                self.assertGreater(colors[1][2], colors[1][0])
                    finally:
                        renderer.close()

        geometry = build_scene_geometry(
            ChartConfig(width=320, height=180),
            FunFactConfig(),
            Scene(title="", bars=[rising]),
        )
        self.assertEqual(geometry["bar_rects"][0]["height"], rising.height)

    def test_rank_motion_pixel_composition_puts_rising_bar_on_top(self):
        config = ChartConfig(
            width=120,
            height=80,
            dpi=72,
            left_margin=0,
            right_margin=0,
            top_margin=0,
            bottom_margin=0,
            title_enabled=False,
            subtitle_enabled=False,
            source_label_enabled=False,
            time_label_enabled=False,
            category_labels_enabled=False,
            value_labels_enabled=False,
            rank_labels_enabled=False,
            logos_enabled=False,
            bar_shadow_enabled=False,
            bar_gradient_enabled=False,
            bar_shape="rectangle",
            background_color_override="#FFFFFF",
        )
        falling = BarSprite(
            name="Falling", value=1, color="#FF0000",
            x=10, y=40, width=100, height=20, rank=2,
            rank_motion_state="falling", rank_motion_progress=0.5,
            rank_motion_target=2,
        )
        rising = replace(
            falling,
            name="Rising",
            color="#0000FF",
            rank=1,
            rank_motion_state="rising",
            rank_motion_target=1,
        )
        renderer = BarRenderer(config=config)
        try:
            rgba = renderer.render_rgba(
                Scene(title="", bars=[rising, falling])
            )
        finally:
            renderer.close()
        image = Image.frombytes("RGBA", (config.width, config.height), rgba)

        self.assertEqual(image.getpixel((60, 40))[:3], (0, 0, 255))

    def test_rank_motion_keeps_primary_logo_at_nominal_height(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "logo.png"
            Image.new("RGBA", (32, 32), (20, 120, 220, 255)).save(logo_path)
            item = BarSprite(
                name="Rising",
                value=100,
                color="#123456",
                x=40,
                y=60,
                width=120,
                height=20,
                rank=1,
                logo_path=str(logo_path),
                rank_motion_state="rising",
                rank_motion_progress=0.5,
                rank_motion_target=1,
            )
            renderer = BarRenderer(config=ChartConfig(
                width=240,
                height=120,
                dpi=72,
                logos_enabled=True,
                logo_size=100,
                bar_logo_position="inside_right",
                bar_appearance_mode="advanced",
                title_enabled=False,
                subtitle_enabled=False,
                source_label_enabled=False,
                time_label_enabled=False,
                category_labels_enabled=False,
                value_labels_enabled=False,
                rank_labels_enabled=False,
            ))
            try:
                renderer.render_rgba(Scene(title="", bars=[item]))
                logo_image = renderer._logo_composite_artist.commands[0][0]
                bar_image = renderer._advanced_composite_artist.commands[0][0]
            finally:
                renderer.close()

        self.assertEqual(rank_motion_effective_height(item), 24)
        self.assertEqual(logo_image.shape[:2], (20, 20))
        self.assertEqual(bar_image.shape[0], 24)

    def test_rank_motion_swap_matches_preview_and_render_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "data.csv").write_text(
                "year,name,value\n"
                "0,A,100\n0,B,90\n"
                "1,A,80\n1,B,110\n",
                encoding="utf-8",
            )
            project_data = self._project_data(
                steps_per_transition=4,
                top_n=2,
                max_visible_bars=2,
                motion_mode="continuous",
            )
            project_data["chart"].update({
                "width": 320,
                "height": 180,
                "frame_output_mode": "png_sequence",
                "auto_fit_bar_count": False,
            })
            preset = resolve_project_preset_paths(
                load_project_data(project_data),
                project_root=root,
                output_root=root,
            )
            with patch("pipeline.render_job.BarRenderer") as render_renderer:
                with patch("pipeline.render_job.VideoExporter"):
                    with patch("builtins.print"):
                        RenderJob(
                            config=preset.chart_config,
                            data_source_config=preset.data_source_config,
                            dataset_config=preset.dataset_config,
                            fun_fact_config=preset.fun_fact_config,
                            export_config=preset.export_config,
                            project_root=root,
                            output_file_is_effective=True,
                        ).run()
            render_scene = (
                render_renderer.return_value.render.call_args_list[2].args[0]
            )

            with patch("studio.preview.BarRenderer") as preview_renderer:
                preview_renderer.return_value.render.return_value = str(
                    root / "preview.png"
                )
                render_project_preview(
                    root / "project.json",
                    output_dir=root / "previews",
                    root_dir=root,
                    project_data=project_data,
                    preview_mode="transition",
                    year=0,
                    transition_progress=0.5,
                )
            preview_scene = preview_renderer.return_value.render.call_args.args[0]

        self.assertEqual(render_scene.bars, preview_scene.bars)
        self.assertEqual(
            [rank_motion_effective_height(item) for item in render_scene.bars],
            [rank_motion_effective_height(item) for item in preview_scene.bars],
        )

    def test_primary_logo_minimum_is_capped_by_bar_height(self):
        renderer = BarRenderer(config=ChartConfig(
            width=200, height=100, bar_logo_position="inside_left",
            logo_size=20, primary_logo_min_size=100,
        ))
        try:
            layout = renderer._base_logo_layout(
                BarSprite(
                    name="Tiny", value=1, color="#000000", x=20, y=50,
                    width=12, height=20, rank=1, logo_path="logo.png",
                ),
                slot="primary",
            )
        finally:
            renderer.close()
        self.assertEqual(layout["size"], 20)
        self.assertGreater(layout["size"], 12)
        self.assertEqual(layout["left"], 20)
        self.assertGreaterEqual(layout["left"], 0)
        self.assertLessEqual(layout["right"], 200)

    def test_short_primary_logo_anchors_outer_badge_at_bar_start(self):
        item = BarSprite(
            name="Tiny", value=1, color="#000000", x=100, y=100,
            width=12, height=48, rank=1, logo_path="logo.png",
        )
        for shape in ("adaptive", "circle", "square"):
            with self.subTest(shape=shape):
                config = ChartConfig(
                    width=400,
                    height=240,
                    bar_appearance_mode="advanced",
                    bar_logo_position="inside_right",
                    bar_logo_shape=shape,
                    logo_size=100,
                    primary_logo_min_size=36,
                    bar_logo_padding=7,
                    bar_logo_border_enabled=True,
                    bar_logo_border_width=4,
                    bar_value_position="outside",
                )
                renderer = BarRenderer(config=config)
                try:
                    layout = renderer._logo_layout(item)
                    value_layout = renderer._value_label_layout(item, "1")
                    geometry = build_scene_geometry(
                        config,
                        FunFactConfig(),
                        Scene(title="", bars=[item]),
                    )
                finally:
                    renderer.close()

                logo_rect = geometry["primary_logo_rects"][0]
                self.assertEqual(layout["left"], item.x)
                self.assertEqual(layout["right"], item.x + layout["size"])
                self.assertEqual(logo_rect["x"], item.x)
                self.assertGreaterEqual(layout["left"], item.x)
                self.assertGreaterEqual(
                    value_layout["x"],
                    layout["right"] + config.logo_label_gap,
                )

    def test_normal_primary_logo_keeps_inside_right_alignment(self):
        renderer = BarRenderer(config=ChartConfig(
            width=500,
            height=240,
            bar_logo_position="inside_right",
            logo_size=100,
            primary_logo_min_size=36,
        ))
        try:
            long_bar = BarSprite(
                name="Long", value=100, color="#000000", x=100, y=80,
                width=220, height=48, rank=1, logo_path="logo.png",
            )
            medium_bar = replace(long_bar, name="Medium", width=48, y=150)
            long_layout = renderer._logo_layout(long_bar)
            medium_layout = renderer._logo_layout(medium_bar)
        finally:
            renderer.close()

        self.assertEqual(long_layout["right"], long_bar.x + long_bar.width)
        self.assertEqual(long_layout["left"], 272)
        self.assertEqual(medium_layout["left"], medium_bar.x)
        self.assertEqual(medium_layout["right"], medium_bar.x + medium_bar.width)

    def test_primary_logo_size_depends_on_row_height_not_bar_width(self):
        renderer = BarRenderer(config=ChartConfig(
            width=800,
            height=300,
            bar_logo_position="inside_right",
            logo_size=100,
            primary_logo_min_size=0,
            value_labels_enabled=True,
            bar_appearance_mode="advanced",
            bar_value_position="outside",
        ))
        try:
            layouts = []
            for width in (500, 100, 30, 10, 2):
                item = BarSprite(
                    name="Row", value=width, color="#000000",
                    x=100, y=100, width=width, height=48,
                    rank=1, logo_path="logo.png",
                )
                layout = renderer._logo_layout(item)
                value_layout = renderer._value_label_layout(item, "100")
                layouts.append(layout)
                self.assertEqual(layout["size"], 48)
                self.assertGreaterEqual(
                    value_layout["x"],
                    layout["right"] + renderer.config.logo_label_gap,
                )
            self.assertEqual(
                {round(layout["size"], 6) for layout in layouts},
                {48.0},
            )

            original = BarSprite(
                name="Row", value=100, color="#000000", x=100, y=100,
                width=500, height=48, rank=1, logo_path="logo.png",
            )
            scaled = None
            for mode in ("static", "dynamic"):
                axis_config = replace(
                    renderer.config,
                    value_grid_enabled=True,
                    value_grid_mode=mode,
                )
                raw = [replace(original, width=10)]
                bar_scale = BarValueScaleResolver.from_config(
                    axis_config, [[original]]
                ).for_sprites(raw)
                scaled = scale_bar_sprites(
                    raw,
                    bar_scale,
                )[0]
                self.assertEqual(
                    renderer._logo_layout(original)["size"],
                    renderer._logo_layout(scaled)["size"],
                )

            geometry = build_scene_geometry(
                renderer.config,
                FunFactConfig(),
                Scene(title="", subtitle="", bars=[scaled]),
            )
            self.assertEqual(
                geometry["primary_logo_rects"][0]["width"],
                renderer._logo_layout(scaled)["size"],
            )
        finally:
            renderer.close()

    def test_primary_logo_size_is_percentage_of_bar_height(self):
        item = BarSprite(
            name="Row", value=1, color="#000000", x=100, y=100,
            width=10, height=48, rank=1, logo_path="logo.png",
        )
        for percent, expected in ((100, 48), (75, 36), (50, 24), (25, 12)):
            with self.subTest(percent=percent):
                renderer = BarRenderer(config=ChartConfig(
                    width=300,
                    height=200,
                    logo_size=percent,
                    bar_logo_position="inside_right",
                ))
                try:
                    layout = renderer._logo_layout(item)
                finally:
                    renderer.close()
                self.assertEqual(layout["size"], expected)

    def test_primary_outer_badge_contains_padding_border_and_shapes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = Path(temp_dir) / "logo.png"
            Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(logo_path)
            item = BarSprite(
                name="Row", value=1, color="#000000", x=100, y=100,
                width=2, height=48, rank=1, logo_path=str(logo_path),
            )
            for shape in ("adaptive", "circle", "square"):
                with self.subTest(shape=shape):
                    renderer = BarRenderer(config=ChartConfig(
                        width=300,
                        height=200,
                        logo_size=100,
                        bar_logo_position="inside_right",
                        bar_logo_shape=shape,
                        bar_logo_padding=7,
                        bar_logo_background_enabled=True,
                        bar_logo_border_enabled=True,
                        bar_logo_border_width=4,
                    ))
                    try:
                        layout = renderer._logo_layout(item)
                        command = renderer._logo_composite_command(
                            item, layout=layout
                        )
                        geometry = build_scene_geometry(
                            renderer.config,
                            FunFactConfig(),
                            Scene(title="", bars=[item]),
                        )
                    finally:
                        renderer.close()

                    image = command[0]
                    artwork = (
                        (image[:, :, 0] > 180)
                        & (image[:, :, 1] < 100)
                        & (image[:, :, 2] < 100)
                    )
                    artwork_columns = artwork.any(axis=0).nonzero()[0]
                    self.assertEqual(layout["size"], 48)
                    self.assertLessEqual(image.shape[0], 48)
                    self.assertLessEqual(image.shape[1], 48)
                    self.assertLessEqual(
                        artwork_columns[-1] - artwork_columns[0] + 1,
                        48 - 14,
                    )
                    self.assertEqual(
                        geometry["primary_logo_rects"][0]["height"],
                        layout["size"],
                    )
                    self.assertEqual(image.shape[0], round(layout["size"]))

    def test_secondary_logo_retains_width_capped_sizing(self):
        renderer = BarRenderer(config=ChartConfig(
            width=300,
            height=200,
            bar_secondary_logo_enabled=True,
            bar_secondary_logo_layout="independent",
            bar_secondary_logo_position="inside_left",
            bar_secondary_logo_size=40,
            bar_secondary_logo_padding=3,
        ))
        try:
            item = BarSprite(
                name="Row", value=1, color="#000000", x=50, y=80,
                width=10, height=48, rank=1,
                secondary_logo_path="secondary.png",
            )
            secondary = renderer._base_logo_layout(item, slot="secondary")
        finally:
            renderer.close()

        self.assertEqual(secondary["size"], 4)

    def test_primary_logo_height_floor_renders_in_both_aspect_ratios(self):
        for width, height in ((320, 180), (180, 320)):
            with self.subTest(width=width, height=height):
                renderer = BarRenderer(config=ChartConfig(
                    width=width,
                    height=height,
                    bar_logo_position="inside_right",
                    logo_size=100,
                ))
                item = BarSprite(
                    name="Row", value=1, color="#000000",
                    x=20, y=90, width=10, height=48,
                    rank=1, logo_path="logo.png",
                )
                try:
                    layout = renderer._logo_layout(item)
                    rgba = renderer.render_rgba(Scene(title="", bars=[item]))
                finally:
                    renderer.close()

                self.assertEqual(layout["size"], 48)
                self.assertEqual(layout["left"], item.x)
                self.assertGreaterEqual(layout["left"], 0)
                self.assertLessEqual(layout["right"], width)
                self.assertEqual(len(rgba), width * height * 4)

    def test_small_primary_logo_matches_preview_and_render_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logo_path = root / "logo.png"
            csv_path = root / "data.csv"
            Image.new("RGBA", (32, 32), (20, 120, 220, 255)).save(logo_path)
            csv_path.write_text(
                "year,name,value\n"
                "0,Leader,1000\n0,Tiny,1\n"
                "1,Leader,1100\n1,Tiny,2\n",
                encoding="utf-8",
            )
            project_data = self._project_data(
                csv_path="data.csv",
                steps_per_transition=2,
                top_n=2,
                max_visible_bars=2,
                category_styles={
                    "Leader": {"logo": "logo.png"},
                    "Tiny": {"logo": "logo.png"},
                },
            )
            project_data["chart"].update({
                "width": 640,
                "height": 360,
                "frame_output_mode": "png_sequence",
                "auto_fit_bar_count": False,
                "bar_logo_position": "inside_right",
                "logo_size": 100,
                "primary_logo_min_size": 36,
            })
            preset = resolve_project_preset_paths(
                load_project_data(project_data),
                project_root=root,
                output_root=root,
            )

            with patch("pipeline.render_job.BarRenderer") as render_renderer:
                with patch("pipeline.render_job.VideoExporter"):
                    with patch("builtins.print"):
                        RenderJob(
                            config=preset.chart_config,
                            data_source_config=preset.data_source_config,
                            dataset_config=preset.dataset_config,
                            fun_fact_config=preset.fun_fact_config,
                            export_config=preset.export_config,
                            project_root=root,
                            output_file_is_effective=True,
                        ).run()
            render_scene = render_renderer.return_value.render.call_args_list[0].args[0]

            with patch("studio.preview.BarRenderer") as preview_renderer:
                preview_renderer.return_value.render.return_value = str(
                    root / "preview.png"
                )
                render_project_preview(
                    root / "project.json",
                    output_dir=root / "previews",
                    root_dir=root,
                    project_data=project_data,
                    year=0,
                )
            preview_scene = preview_renderer.return_value.render.call_args.args[0]
            render_bar = next(bar for bar in render_scene.bars if bar.name == "Tiny")
            preview_bar = next(bar for bar in preview_scene.bars if bar.name == "Tiny")
            renderer = BarRenderer(config=preset.chart_config)
            try:
                render_layout = renderer._logo_layout(render_bar)
                preview_layout = renderer._logo_layout(preview_bar)
            finally:
                renderer.close()

            self.assertEqual(render_bar, preview_bar)
            self.assertEqual(render_layout, preview_layout)
            self.assertEqual(render_layout["left"], render_bar.x)

    def _project_data(self, **overrides):
        defaults = dict(
            name="test", csv_path="data.csv", year_column="year",
            name_column="name", value_column="value", title="Test",
            source_label="Source", output_file="out.mp4", frames_dir="frames",
            layout_preset="youtube_1080p", theme="clean_report",
            typography_preset="studio", value_format="decimal", fps=30,
            steps_per_transition=30, top_n=5, max_visible_bars=5,
        )
        defaults.update(overrides)
        return build_project_data(**defaults)


if __name__ == "__main__":
    unittest.main()
