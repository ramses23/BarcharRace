import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import _test_path
import numpy as np
from PIL import Image

from config.chart_config import ChartConfig
from models.bar_sprite import BarSprite
from models.scene import Scene
from models.value_axis import GridDisplayScale, ValueAxisState, ValueAxisTick
from renderer.bar_renderer import BarRenderer
from renderer.subpixel import FloatImageCommand, rasterize_image_command


class SubpixelMotionTest(unittest.TestCase):
    def test_rendered_gradient_has_no_strip_seams_and_moves_subpixel(self):
        config = ChartConfig(width=320, height=240, dpi=72,
            background_color_override="#000000", bar_appearance_mode="simple",
            bar_shape="rectangle", bar_gradient_enabled=True,
            logos_enabled=False, rank_labels_enabled=False, category_labels_enabled=False,
            value_labels_enabled=False, title_enabled=False, source_label_enabled=False,
            time_label_enabled=False, bar_shadow_enabled=False, bar_border_enabled=False)
        renderer = BarRenderer(config=config)
        try:
            centers = []
            for y in (80.1, 80.3, 80.5, 80.7, 80.9, 81.1):
                sprite = BarSprite(name="", value=1, color="#CC3300",
                    x=50, y=y, width=180, height=32)
                pixels = np.frombuffer(renderer.render_rgba(Scene(title="", bars=[sprite])),
                    dtype=np.uint8).reshape(240, 320, 4)
                red = pixels[:, 60:220, 0].astype(float)
                # Adjacent strips must not reveal black vertical seams.
                self.assertLess(np.abs(np.diff(red[80])).max(), 3)
                weights = red.sum(axis=1)
                centers.append(np.dot(weights, np.arange(240) + .5) / weights.sum())
            np.testing.assert_allclose(np.diff(centers), .2, atol=.015)
        finally:
            renderer.close()

    def test_axis_grid_and_label_receive_same_float_scale_delta(self):
        config = ChartConfig(width=320, height=240, value_grid_enabled=True)
        renderer = BarRenderer(config=config)
        try:
            previous = None
            for x in (100.1, 100.3, 100.5, 100.7, 100.9, 101.1):
                axis = ValueAxisState(GridDisplayScale(0, x * 2, 100),
                    (ValueAxisTick(50, x, "50"),), 50, 50, 200, 30.25)
                renderer.render_rgba(Scene(title="", bars=[], value_axis=axis))
                self.assertIs(renderer._value_grid_collection.get_snap(), False)
                self.assertAlmostEqual(renderer._value_grid_collection.get_segments()[0][0][0], x)
                command = renderer._value_tick_composite_artist.commands[0]
                if previous is not None:
                    self.assertAlmostEqual(command[1] - previous[1], .2)
                    self.assertEqual(command[2], previous[2])
                previous = command
            renderer.render_rgba(Scene(title="", bars=[]))
            self.assertFalse(renderer._value_tick_composite_artist.commands)
        finally:
            renderer.close()

    def test_fractional_translation_has_no_stall_or_jump_at_integer_boundary(self):
        source = np.full((12, 16, 4), 255, dtype=np.uint8)
        centers = []
        for top in (100.1, 100.3, 100.5, 100.7, 100.9, 101.1):
            pixels, left, y = rasterize_image_command((source, 10, top))
            weights = pixels[::-1, :, 3].sum(axis=1).astype(float)
            centers.append(y + np.dot(weights, np.arange(len(weights)) + .5) / weights.sum())
        np.testing.assert_allclose(np.diff(centers), .2, atol=.006)
        np.testing.assert_allclose(centers, np.array((100.1, 100.3, 100.5, 100.7, 100.9, 101.1)) + 6, atol=.006)

    def test_integer_identity_is_exact_and_transparent_rgb_does_not_bleed(self):
        source = np.zeros((12, 16, 4), dtype=np.uint8)
        source[:, :, 2] = 255
        source[3:9, 3:13] = (255, 0, 0, 255)
        self.assertIs(rasterize_image_command((source, 4, 5))[0], source)
        pixels, _, _ = rasterize_image_command(FloatImageCommand(source, -1.3, 5.7, .9))
        visible = pixels[:, :, 3] > 0
        self.assertTrue(visible.any())
        self.assertTrue((pixels[visible, 2] == 0).all())
        self.assertTrue((pixels[visible, 0] == 255).all())

    def test_both_logos_text_and_body_share_fractional_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logo.png"
            Image.new("RGBA", (32, 32), "red").save(path)
            for fill in ("solid", "gradient", "texture"):
                config = ChartConfig(width=320, height=240, left_margin=50,
                    right_margin=20, top_margin=40, bottom_margin=20,
                    bar_appearance_mode="unified", bar_fill_type=fill,
                    bar_texture_enabled=fill == "texture",
                    bar_logo_position="inside_left", logo_size=100,
                    bar_secondary_logo_enabled=True, bar_secondary_logo_size=16,
                    bar_secondary_logo_layout="side_by_side")
                renderer = BarRenderer(config=config)
                try:
                    rows = []
                    for y in (80.1, 80.3, 80.5, 80.7, 80.9, 81.1):
                        sprite = BarSprite(name="Alpha", value=100, color="#CC3300",
                            x=50.25, y=y, width=180.35, height=32, rank=1,
                            logo_path=str(path), secondary_logo_path=str(path))
                        renderer.render_rgba(Scene(title="", bars=[sprite]))
                        visual, logo_sprite = renderer._final_visual_geometry(sprite)
                        commands = [renderer._logo_composite_command(logo_sprite,
                            slot=slot, logo_path=p, layout=layout)
                            for slot, p, layout, _ in renderer._logo_layouts_for_sprite(logo_sprite)]
                        self.assertEqual(len(commands), 2)
                        rows.append((visual.y, [c.top for c in commands],
                            [c.image.shape for c in commands],
                            [c[2] for c in renderer._bar_text_commands(visual)]))
                    for previous, current in zip(rows, rows[1:]):
                        self.assertEqual(previous[2], current[2])
                        np.testing.assert_allclose(np.subtract(current[1], previous[1]), .2, atol=1e-10)
                        np.testing.assert_allclose(np.subtract(current[3], previous[3]), .2, atol=1e-10)
                        self.assertAlmostEqual(current[0] - previous[0], .2)
                finally:
                    renderer.close()


if __name__ == "__main__":
    unittest.main()
