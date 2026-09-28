import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import _test_path
import numpy as np
import pandas as pd
from PIL import Image

from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from config.chart_config import ChartConfig
from config.fun_fact_config import FunFactConfig
from config.project_file_loader import load_project_data, load_project_file
from core.layout_engine import LayoutEngine
from core.scene_geometry import build_scene_geometry
from models.bar_data import BarData
from models.bar_sprite import BarSprite
from models.fun_fact import ActiveFunFact, FunFact
from models.scene import Scene
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from studio.appearance_presets import build_appearance_preset, apply_appearance_preset
from studio.fun_fact_layout import editorial_block_geometry, editorial_obstacle_rects
from studio.project_builder import project_form_values


class IndependentEditorialBlocksTest(unittest.TestCase):
    def setUp(self):
        self.chart = ChartConfig(
            width=1000, height=600, dpi=72, left_margin=80, right_margin=60,
            title_enabled=False, subtitle_enabled=False,
            source_label_enabled=False, time_label_enabled=False,
            category_labels_enabled=False, value_labels_enabled=False,
            rank_labels_enabled=False, logos_enabled=False,
        )
        self.config = FunFactConfig(
            enabled=True, layout="editorial_floating",
            editorial_composition="independent", editorial_layout_mode="reserved",
            editorial_text_x=650, editorial_text_y=100,
            editorial_text_width=300, editorial_text_height=160,
            editorial_image_x=400, editorial_image_y=400,
            editorial_image_width=220, editorial_image_height=150,
        )
        self.bar = BarSprite("Leader", 100, "#2677BB", 80, 180, 420, 44, rank=1)

    def test_card_default_renders_identically_to_explicit_card(self):
        legacy = replace(self.config, editorial_composition="card")
        scene = Scene(title="", bars=[self.bar], fun_fact=ActiveFunFact(
            FunFact("a", "2000", "2000", "Headline", "Body"), 1.0,
        ))
        images = []
        for config in (legacy, replace(legacy, editorial_text_x=100)):
            renderer = BarRenderer(config=self.chart, fun_fact_config=config)
            try:
                images.append(renderer.render_rgba(scene))
            finally:
                renderer.close()
        self.assertTrue(np.array_equal(*images))
        self.assertEqual(FunFactConfig().editorial_composition, "card")

    def test_independent_geometry_round_trips_and_style_edits_do_not_move_it(self):
        fields = {field: getattr(self.config, field) for field in (
            "editorial_composition", "editorial_text_x", "editorial_text_y",
            "editorial_text_width", "editorial_text_height", "editorial_image_x",
            "editorial_image_y", "editorial_image_width", "editorial_image_height",
        )}
        data = {"name": "blocks", "fun_facts": fields}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "project.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            loaded = load_project_file(path).fun_fact_config
        self.assertEqual(loaded.editorial_composition, "independent")
        for field, value in fields.items():
            self.assertEqual(getattr(loaded, field), value)
            self.assertEqual(project_form_values(data)[f"fun_facts_{field}"], value)
        preset = build_appearance_preset("Blocks", data)
        applied = apply_appearance_preset({"name": "target"}, preset)
        self.assertEqual({field: applied["fun_facts"][field] for field in fields}, fields)
        original = [editorial_block_geometry(self.chart, loaded, block)
                    for block in ("text", "image")]
        for changed in (
            replace(loaded, editorial_body_size=32),
            replace(loaded, editorial_headline_size=42),
            replace(loaded, editorial_image_fit="cover"),
            replace(loaded, editorial_background_color="#123456"),
        ):
            self.assertEqual(original, [editorial_block_geometry(self.chart, changed, block)
                                        for block in ("text", "image")])
        self.assertEqual(
            editorial_block_geometry(self.chart, replace(loaded, editorial_text_x=680), "image"),
            original[1],
        )
        self.assertEqual(
            editorial_block_geometry(self.chart, replace(loaded, editorial_image_x=450), "text"),
            original[0],
        )

    def test_two_obstacles_are_separate_and_absent_image_is_not_reserved(self):
        all_rects = editorial_obstacle_rects(self.chart, self.config)
        self.assertEqual(all_rects, ((650, 100, 300, 160), (400, 400, 220, 150)))
        self.assertEqual(editorial_obstacle_rects(self.chart, self.config, has_image=False),
                         (all_rects[0],))
        bars = [BarData("A", 100), BarData("B", 80), BarData("C", 60)]
        centers = (180, 330, 460)
        full = LayoutEngine(self.chart, self.config)._max_bar_width(
            bars, row_centers=centers, bar_height=44, max_value=100,
        )
        no_image = LayoutEngine(self.chart, self.config, editorial_image_present=False)._max_bar_width(
            bars, row_centers=centers, bar_height=44, max_value=100,
        )
        self.assertLessEqual(80 + full * .6, 400 - 24)
        self.assertLessEqual(80 + full, 650 - 24)
        self.assertGreater(80 + full, 400 - 24)  # Free gap, not giant bounding box.
        self.assertGreater(no_image, full)
        fact = ActiveFunFact(FunFact("a", "2000", "2000", "Text"), 1.0)
        geometry = build_scene_geometry(self.chart, self.config, Scene(
            title="", bars=[self.bar], fun_fact=fact,
        ))
        self.assertIsNone(geometry["editorial_block_rects"]["image"])
        self.assertEqual(len(geometry["collision_rects"]), 1)

    def test_image_content_is_independent_and_pulse_targets_text(self):
        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "image.png"
            Image.new("RGB", (120, 90), "#DA9352").save(image_path)
            fact = FunFact("a", "2000", "2000", "Headline", "Body",
                           image_path=str(image_path), anchor_category="Leader")
            scene = Scene(title="", bars=[self.bar],
                          fun_fact=ActiveFunFact(fact, 1.0, age_frames=60), frame_index=60)
            config = replace(self.config, data_link="data_pulse")
            renderer = BarRenderer(config=self.chart, fun_fact_config=config)
            try:
                first = renderer.render_rgba(scene)
                commands = renderer._fun_fact_artist.commands
                self.assertEqual(len(commands), 2)
                self.assertEqual(commands[0][1:], (650, 100))
                self.assertEqual(commands[1][1:], (400, 400))
                self.assertAlmostEqual(renderer._fun_fact_link.get_path().vertices[-1, 0], 659)
                self.assertAlmostEqual(renderer._fun_fact_link.get_path().vertices[-1, 1], 104.8)
                text_pixels = commands[0][0].copy()
                image_pixels = commands[1][0].copy()
                other = replace(scene, frame_index=100)
                renderer.render_rgba(other)
                second = renderer.render_rgba(scene)
                self.assertTrue(np.array_equal(first, second))
            finally:
                renderer.close()
            cover = BarRenderer(config=self.chart, fun_fact_config=replace(
                config, editorial_image_fit="cover",
            ))
            try:
                cover.render_rgba(scene)
                self.assertTrue(np.array_equal(text_pixels, cover._fun_fact_artist.commands[0][0]))
                self.assertFalse(np.array_equal(image_pixels, cover._fun_fact_artist.commands[1][0]))
            finally:
                cover.close()
        self.assertEqual(load_project_data({"name": "legacy"}).fun_fact_config.editorial_composition,
                         "card")

    def test_partial_render_matches_global_frame_with_independent_pulse(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pd.DataFrame({
                "year": [2000, 2001], "name": ["Leader", "Leader"],
                "value": [100, 150],
            }).to_csv(root / "data.csv", index=False)
            (root / "facts.json").write_text(json.dumps({
                "version": 1, "fun_facts": [{
                    "id": "a", "start": "2000", "end": "2000",
                    "headline": "The story", "anchor_category": "Leader",
                }],
            }), encoding="utf-8")
            chart = replace(self.chart, width=640, height=360, fps=30,
                            left_margin=40, right_margin=40,
                            steps_per_transition=90,
                            output_file=str(root / "out.mp4"),
                            frames_dir=str(root / "frames"))
            facts = replace(self.config, source="facts.json",
                            editorial_text_x=380, editorial_text_y=60,
                            editorial_text_width=220, editorial_text_height=140,
                            editorial_image_x=260, editorial_image_y=220,
                            editorial_image_width=160, editorial_image_height=100,
                            data_link="data_pulse", fade_in=0, fade_out=0)

            def sample(export):
                captured = {}
                def consume(scene, renderer):
                    pixels = renderer.render_rgba(scene)
                    captured[scene.frame_index] = (
                        pixels, renderer._fun_fact_link.get_path().vertices.copy(),
                    )
                RenderJob(
                    config=chart,
                    data_source_config=DataSourceConfig(csv_path=str(root / "data.csv")),
                    dataset_config=DatasetConfig(name_column="name"),
                    fun_fact_config=facts, export_config=export,
                    project_root=root,
                ).run(frame_sampler=lambda _start, _end: (15,), frame_consumer=consume)
                return captured

            full = sample(ExportConfig())
            partial = sample(ExportConfig(render_start_frame=10, render_end_frame=40))
            self.assertEqual(set(full), {15})
            self.assertEqual(full[15][0], partial[15][0])
            self.assertTrue(np.array_equal(full[15][1], partial[15][1]))


if __name__ == "__main__":
    unittest.main()
