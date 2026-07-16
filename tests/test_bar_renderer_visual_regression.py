import hashlib
import unittest

import _test_path
from config.chart_config import ChartConfig
from models.bar_sprite import BarSprite
from models.scene import Scene
from renderer.bar_renderer import BarRenderer


class BarRendererVisualRegressionTest(unittest.TestCase):
    def test_simple_frame_matches_reference_signature(self):
        signature = self._render_signature(
            ChartConfig(
                width=320,
                height=180,
                dpi=72,
                left_margin=96,
                right_margin=28,
                top_margin=52,
                bottom_margin=24,
                title_font_family="DejaVu Sans",
                subtitle_font_family="DejaVu Sans",
                label_font_family="DejaVu Sans",
                value_font_family="DejaVu Sans",
                rank_label_font_family="DejaVu Sans",
                time_label_font_family="DejaVu Sans",
                source_font_family="DejaVu Sans",
                title_font_size=16,
                subtitle_font_size=9,
                label_font_size=9,
                value_font_size=8,
                rank_label_font_size=8,
                time_label_font_size=32,
                source_font_size=6,
                title_y=16,
                subtitle_y=33,
                time_label_x=300,
                time_label_y=151,
                source_x=96,
                source_y=170,
                bar_height=22,
                bar_gap=8,
                logos_enabled=False,
                bar_shape="rounded",
                bar_border_enabled=True,
                bar_border_width=1.25,
                bar_shadow_enabled=True,
                bar_gradient_enabled=True,
            )
        )

        self.assertEqual(
            signature,
            "3ccb229f58f622f252539b710e1f225a5ef1e4a051b018044a29ebefb383180f",
        )

    def test_advanced_frame_matches_reference_signature(self):
        signature = self._render_signature(
            ChartConfig(
                width=320,
                height=180,
                dpi=72,
                left_margin=96,
                right_margin=28,
                top_margin=52,
                bottom_margin=24,
                title_font_family="DejaVu Sans",
                subtitle_font_family="DejaVu Sans",
                label_font_family="DejaVu Sans",
                value_font_family="DejaVu Sans",
                rank_label_font_family="DejaVu Sans",
                time_label_font_family="DejaVu Sans",
                source_font_family="DejaVu Sans",
                title_font_size=16,
                subtitle_font_size=9,
                label_font_size=9,
                value_font_size=8,
                rank_label_font_size=8,
                time_label_font_size=32,
                source_font_size=6,
                title_y=16,
                subtitle_y=33,
                time_label_x=300,
                time_label_y=151,
                source_x=96,
                source_y=170,
                bar_height=22,
                bar_gap=8,
                logos_enabled=False,
                bar_appearance_mode="advanced",
                bar_shape="capsule",
                bar_fill_type="texture",
                bar_texture_enabled=True,
                bar_texture_preset="carbon",
                bar_texture_intensity=0.35,
                bar_bevel_enabled=True,
                bar_inner_shadow_opacity=0.2,
                bar_outer_glow_enabled=True,
                bar_glow_opacity=0.25,
                bar_shine_enabled=True,
                bar_track_enabled=True,
                bar_border_enabled=True,
                bar_border_width=1.25,
            )
        )

        self.assertEqual(
            signature,
            "1525011b36259d758147224be791c89cc9ac70e26b312862aa850e7fb715ff66",
        )

    @staticmethod
    def _render_signature(config):
        renderer = BarRenderer(config=config)
        scene = Scene(
            title="Visual reference",
            subtitle="Stable renderer contract",
            time_label="2026",
            source_label="Source: fixture",
            bars=[
                BarSprite(
                    name="Alpha",
                    value=125,
                    color="#4E79A7",
                    x=96,
                    y=76,
                    width=176,
                    height=22,
                    rank=1,
                ),
                BarSprite(
                    name="Beta",
                    value=84,
                    color="#F28E2B",
                    x=96,
                    y=108,
                    width=118,
                    height=22,
                    rank=2,
                ),
            ],
        )

        try:
            rgba = renderer.render_rgba(scene)
        finally:
            renderer.close()

        return hashlib.sha256(rgba).hexdigest()


if __name__ == "__main__":
    unittest.main()
