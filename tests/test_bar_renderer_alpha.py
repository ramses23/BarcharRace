import unittest

import _test_path
import numpy as np

from config.chart_config import ChartConfig
from config.theme_config import ThemeConfig
from models.bar_sprite import BarSprite
from models.scene import Scene
from models.value_axis import ValueAxisState, ValueAxisTick, ValueScale
from renderer.bar_renderer import BarRenderer


class BarRendererAlphaTest(unittest.TestCase):
    def test_solid_vector_fill_alpha_is_independent_of_bar_width(self):
        config = self._config()
        sprites = self._sprites(config, opacity=1.0)
        renderer = BarRenderer(config=config)
        try:
            renderer._draw_scene(Scene(title="", bars=sprites), draw_canvas=True)
            alphas = [
                artists.bar.get_facecolor()[3]
                for artists in renderer._bar_artists
            ]
        finally:
            renderer.close()

        self.assertEqual(alphas, [1.0, 1.0, 1.0, 1.0])

    def test_solid_vector_fill_preserves_animation_opacity_for_every_width(self):
        config = self._config()
        sprites = self._sprites(config, opacity=0.5)
        renderer = BarRenderer(config=config)
        try:
            renderer._draw_scene(Scene(title="", bars=sprites), draw_canvas=True)
            alphas = [
                artists.bar.get_facecolor()[3]
                for artists in renderer._bar_artists
            ]
        finally:
            renderer.close()

        self.assertEqual(alphas, [0.5, 0.5, 0.5, 0.5])

    def test_vector_gradient_fill_alpha_is_independent_of_bar_width(self):
        for opacity in (1.0, 0.5):
            with self.subTest(opacity=opacity):
                config = self._config(
                    bar_fill_type="gradient",
                    bar_gradient_enabled=True,
                    bar_gradient_direction="horizontal",
                    bar_gradient_color_count=2,
                )
                renderer = BarRenderer(config=config)
                try:
                    renderer._draw_scene(
                        Scene(
                            title="",
                            bars=self._sprites(config, opacity=opacity),
                        ),
                        draw_canvas=True,
                    )
                    alphas = renderer._gradient_artist.get_facecolors()[:, 3]
                finally:
                    renderer.close()

                self.assertTrue(np.allclose(alphas, opacity))

    def test_advanced_material_alpha_depends_only_on_animation_opacity(self):
        config = self._config(bar_appearance_mode="advanced")
        renderer = BarRenderer(config=config)
        try:
            for opacity, expected_alpha in ((1.0, 255), (0.5, 128)):
                for sprite in self._sprites(config, opacity=opacity):
                    with self.subTest(opacity=opacity, width=sprite.width):
                        composite, _ = renderer._compose_advanced_sprite(sprite)
                        center_alpha = composite[
                            composite.shape[0] // 2,
                            composite.shape[1] // 2,
                            3,
                        ]
                        self.assertEqual(int(center_alpha), expected_alpha)
        finally:
            renderer.close()

    def test_opaque_solid_bar_hides_gridline_in_final_pixels(self):
        axis = ValueAxisState(
            scale=ValueScale(origin_x=20, width=160, domain_max=160),
            ticks=(ValueAxisTick(value=40, x=60, label="", opacity=1.0),),
            tick_step=40,
            line_top=10,
            line_bottom=110,
            label_y=5,
        )
        sprite = BarSprite(
            name="Stable",
            value=80,
            color="#FF0000",
            x=20,
            y=60,
            width=80,
            height=30,
            rank=1,
            opacity=1.0,
        )
        scene = Scene(title="", bars=[sprite], value_axis=axis)
        grid_on = self._render_pixels(
            self._config(
                value_grid_enabled=True,
                value_grid_line_color="#000000",
                value_grid_line_opacity=1.0,
                value_grid_line_thickness=6.0,
            ),
            scene,
        )
        grid_off = self._render_pixels(
            self._config(value_grid_enabled=False),
            scene,
        )

        self.assertEqual(tuple(grid_on[10, 10]), (255, 255, 255, 255))
        self.assertEqual(tuple(grid_on[20, 60]), (0, 0, 0, 255))
        self.assertEqual(tuple(grid_on[60, 60]), (255, 0, 0, 255))
        self.assertEqual(tuple(grid_off[60, 60]), (255, 0, 0, 255))

    @staticmethod
    def _config(**overrides):
        defaults = dict(
            width=200,
            height=160,
            dpi=100,
            left_margin=20,
            right_margin=20,
            top_margin=30,
            bottom_margin=20,
            theme=ThemeConfig(
                background_color="#FFFFFF",
                text_color="#000000",
                muted_text_color="#000000",
            ),
            background_color_override="#FFFFFF",
            bar_appearance_mode="unified",
            bar_fill_type="solid",
            bar_fill_use_category_color=True,
            bar_gradient_enabled=False,
            bar_border_enabled=False,
            bar_shadow_enabled=False,
            bar_texture_enabled=False,
            bar_bevel_enabled=False,
            bar_inner_shadow_opacity=0.0,
            bar_top_highlight_opacity=0.0,
            bar_bottom_shade_opacity=0.0,
            bar_outer_glow_enabled=False,
            bar_inner_glow_opacity=0.0,
            bar_shine_enabled=False,
            bar_track_enabled=False,
            title_enabled=False,
            subtitle_enabled=False,
            time_label_enabled=False,
            source_label_enabled=False,
            rank_labels_enabled=False,
            category_labels_enabled=False,
            value_labels_enabled=False,
            value_grid_tick_labels_enabled=False,
        )
        defaults.update(overrides)
        return ChartConfig(**defaults)

    @staticmethod
    def _sprites(config, *, opacity):
        return [
            BarSprite(
                name=f"Width {fraction}",
                value=fraction,
                color="#FF0000",
                x=config.left_margin,
                y=25 + (index * 35),
                width=config.max_bar_width * fraction,
                height=24,
                rank=index + 1,
                opacity=opacity,
            )
            for index, fraction in enumerate((1.0, 0.5, 0.25, 0.10))
        ]

    @staticmethod
    def _render_pixels(config, scene):
        renderer = BarRenderer(config=config)
        try:
            return np.frombuffer(
                renderer.render_rgba(scene),
                dtype=np.uint8,
            ).reshape(config.height, config.width, 4).copy()
        finally:
            renderer.close()


if __name__ == "__main__":
    unittest.main()
