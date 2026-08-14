import unittest

import _test_path
from config.chart_config import ChartConfig
from config.fun_fact_config import FunFactConfig
from core.scene_geometry import build_scene_geometry
from models.bar_sprite import BarSprite
from models.scene import Scene
from studio.fun_fact_layout import apply_fun_fact_layout, editorial_geometry


class SceneGeometryTest(unittest.TestCase):
    def test_uses_real_sprite_rows_bars_lanes_and_logos(self):
        config = ChartConfig(
            width=800,
            height=450,
            dpi=72,
            left_margin=180,
            right_margin=80,
            label_min_x=40,
            rank_label_min_x=12,
            rank_label_gap=170,
            logos_enabled=True,
            logo_size=32,
            bar_logo_position="outside_left",
        )
        scene = Scene(
            title="Title",
            subtitle="2024",
            time_label="2024",
            source_label="Source",
            bars=[
                BarSprite(
                    name="Alpha",
                    value=100,
                    color="#123456",
                    x=180,
                    y=150,
                    width=420,
                    height=40,
                    rank=1,
                    logo_path="alpha.png",
                    secondary_logo_path="flag.png",
                ),
                BarSprite(
                    name="Beta",
                    value=50,
                    color="#654321",
                    x=180,
                    y=220,
                    width=210,
                    height=40,
                    rank=2,
                ),
            ],
        )

        geometry = build_scene_geometry(config, FunFactConfig(), scene)

        self.assertEqual(len(geometry["row_rects"]), 2)
        self.assertEqual(geometry["bar_rects"][0]["width"], 420.0)
        self.assertEqual(geometry["data_area"]["x"], 180.0)
        self.assertEqual(geometry["category_lane"]["width"], 140.0)
        self.assertGreaterEqual(geometry["value_lane"]["width"], 0)
        self.assertEqual(len(geometry["primary_logo_rects"]), 1)
        self.assertEqual(len(geometry["secondary_logo_rects"]), 1)
        self.assertIsNone(geometry["editorial_rect"])

    def test_editorial_and_date_geometry_use_effective_layout(self):
        raw = ChartConfig(
            width=1000,
            height=600,
            dpi=72,
            left_margin=180,
            time_label_x=900,
            time_label_y=520,
        )
        facts = FunFactConfig(
            enabled=True,
            layout="editorial_floating",
            editorial_card_x=560,
            editorial_card_y=290,
            editorial_card_width=380,
            editorial_card_height=240,
            editorial_collision_gap=30,
            editorial_reposition_time_label=True,
        )
        effective = apply_fun_fact_layout(raw, facts)
        scene = Scene(
            title="Title",
            subtitle="Period",
            time_label="2024",
            source_label="Source",
            bars=[],
        )

        geometry = build_scene_geometry(effective, facts, scene)

        self.assertEqual(
            tuple(geometry["editorial_rect"][key] for key in ("x", "y", "width", "height")),
            tuple(float(value) for value in editorial_geometry(effective, facts)),
        )
        self.assertEqual(
            geometry["effective_positions"]["date"],
            {"x": effective.time_label_x, "y": effective.time_label_y},
        )
        self.assertEqual(geometry["collision_rect"]["x"], 530.0)


if __name__ == "__main__":
    unittest.main()
