import unittest

import _test_path
from config.chart_config import ChartConfig
from core.bar_appearance import (
    uses_configurable_bar_content,
    uses_material_bar_renderer,
    uses_vector_bar_gradient,
)


class BarAppearanceTest(unittest.TestCase):
    def test_legacy_modes_keep_their_original_renderers(self):
        simple = ChartConfig(
            bar_appearance_mode="simple",
            bar_gradient_enabled=True,
        )
        advanced = ChartConfig(bar_appearance_mode="advanced")

        self.assertFalse(uses_material_bar_renderer(simple))
        self.assertTrue(uses_vector_bar_gradient(simple))
        self.assertFalse(uses_configurable_bar_content(simple))
        self.assertTrue(uses_material_bar_renderer(advanced))
        self.assertFalse(uses_vector_bar_gradient(advanced))
        self.assertTrue(uses_configurable_bar_content(advanced))

    def test_unified_classic_styles_use_vector_renderer(self):
        gradient = ChartConfig(
            bar_appearance_mode="unified",
            bar_fill_type="gradient",
            bar_gradient_direction="horizontal",
            bar_gradient_color_count=2,
            bar_fill_use_category_color=True,
            bar_edge_darkening=0,
        )
        solid = ChartConfig(
            bar_appearance_mode="unified",
            bar_fill_type="solid",
            bar_fill_use_category_color=True,
        )

        self.assertFalse(uses_material_bar_renderer(gradient))
        self.assertTrue(uses_vector_bar_gradient(gradient))
        self.assertFalse(uses_material_bar_renderer(solid))
        self.assertFalse(uses_vector_bar_gradient(solid))
        self.assertTrue(uses_configurable_bar_content(gradient))

    def test_unified_material_features_select_material_renderer(self):
        material_configs = (
            ChartConfig(
                bar_appearance_mode="unified",
                bar_fill_type="gradient",
                bar_gradient_direction="vertical",
                bar_gradient_color_count=2,
            ),
            ChartConfig(
                bar_appearance_mode="unified",
                bar_fill_type="solid",
                bar_fill_use_category_color=False,
            ),
            ChartConfig(
                bar_appearance_mode="unified",
                bar_texture_enabled=True,
            ),
            ChartConfig(
                bar_appearance_mode="unified",
                bar_bevel_enabled=True,
            ),
            ChartConfig(
                bar_appearance_mode="unified",
                bar_outer_glow_enabled=True,
            ),
            ChartConfig(
                bar_appearance_mode="unified",
                bar_track_enabled=True,
            ),
        )

        for config in material_configs:
            with self.subTest(config=config):
                self.assertTrue(uses_material_bar_renderer(config))
                self.assertFalse(uses_vector_bar_gradient(config))


if __name__ == "__main__":
    unittest.main()
