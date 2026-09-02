import unittest
from dataclasses import replace
from datetime import datetime

import _test_path

from config.chart_config import ChartConfig
from config.export_config import ExportConfig
from config.fun_fact_config import FunFactConfig
from core.scene_geometry import build_scene_geometry
from core.source_text_geometry import resolve_source_text_layout
from models.display_calendar import DisplayCalendarState, FlipModuleState
from models.scene import Scene
from renderer.bar_renderer import BarRenderer
from studio.short_export import apply_export_profile
from utils.text_fit import measure_text_width, measurement_font


class SourceTextGeometryTest(unittest.TestCase):
    SOURCE = (
        "Source: Wikimedia Analytics — cumulative English Wikipedia article "
        "pageviews since Jan 2019 (all-access · user traffic)"
    )

    @staticmethod
    def _config(**values):
        defaults = {
            "width": 1920,
            "height": 1080,
            "dpi": 72,
            "source_x": 120,
            "source_y": 1020,
            "source_font_size": 18,
            "source_max_width": 20,
            "value_label_edge_padding": 24,
            "time_label_x": 1800,
            "time_label_y": 850,
            "time_label_font_size": 80,
            "logos_enabled": False,
        }
        defaults.update(values)
        return ChartConfig(**defaults)

    @classmethod
    def _font(cls, config):
        return measurement_font(
            config.source_font_size,
            config.dpi,
            config.source_font_family or config.font_family,
            config.source_font_weight,
            config.source_font_style,
        )

    @staticmethod
    def _calendar(phase=1.0):
        return DisplayCalendarState(
            display_datetime=datetime(2020, 1, 1),
            display_date=datetime(2020, 1, 1).date(),
            year=FlipModuleState("2019", "2020", phase),
            month=FlipModuleState("DEC", "JAN", phase),
            day=FlipModuleState("31", "1", phase),
            frame_index=10,
        )

    def test_full_source_uses_geometric_width_not_legacy_configured_max(self):
        config = self._config(source_max_width=1)
        layout = resolve_source_text_layout(
            config,
            FunFactConfig(),
            self.SOURCE,
        )

        self.assertEqual(layout.fitted_text, self.SOURCE)
        self.assertGreater(layout.full_text_width, config.source_max_width)
        self.assertEqual(
            layout.available_width,
            config.width - config.value_label_edge_padding - config.source_x,
        )

    def test_exact_available_width_does_not_add_ellipsis(self):
        base = self._config()
        text = "Source: exact width"
        width = measure_text_width(text, self._font(base))
        config = replace(
            base,
            width=int(base.source_x + width + base.value_label_edge_padding),
        )
        layout = resolve_source_text_layout(config, FunFactConfig(), text)

        self.assertEqual(layout.available_width, width)
        self.assertEqual(layout.fitted_text, text)

    def test_only_genuinely_excess_text_uses_ellipsis(self):
        config = self._config(width=520)
        layout = resolve_source_text_layout(
            config,
            FunFactConfig(),
            self.SOURCE * 3,
        )

        self.assertTrue(layout.fitted_text.endswith("..."))
        self.assertLessEqual(layout.fitted_text_width, layout.available_width)
        self.assertGreater(layout.full_text_width, layout.available_width)

    def test_nonintersecting_standard_date_does_not_reduce_width(self):
        config = self._config(date_style="standard", time_label_y=850)
        layout = resolve_source_text_layout(
            config,
            FunFactConfig(),
            self.SOURCE,
            time_label="2020",
        )

        date = next(item for item in layout.obstacles if item.name == "date")
        self.assertFalse(date.intersects_source_band)
        self.assertFalse(date.limits_width)

    def test_intersecting_standard_date_reduces_width(self):
        config = self._config(date_style="standard", time_label_y=1020)
        layout = resolve_source_text_layout(
            config,
            FunFactConfig(),
            self.SOURCE,
            time_label="2020",
        )

        date = next(item for item in layout.obstacles if item.name == "date")
        self.assertTrue(date.intersects_source_band)
        self.assertTrue(date.limits_width)
        self.assertEqual(layout.right_limit, date.rect.x - date.gap)

    def test_nonintersecting_flip_calendar_does_not_reduce_width(self):
        config = self._config(
            date_style="flip_calendar",
            time_label_y=820,
        )
        layout = resolve_source_text_layout(
            config,
            FunFactConfig(),
            self.SOURCE,
            display_calendar=self._calendar(0.3),
        )

        date = next(item for item in layout.obstacles if item.name == "date")
        self.assertFalse(date.intersects_source_band)
        self.assertFalse(date.limits_width)

    def test_intersecting_flip_calendar_uses_stable_bbox_without_jitter(self):
        config = self._config(
            date_style="flip_calendar",
            time_label_y=1020,
        )
        layouts = [
            resolve_source_text_layout(
                config,
                FunFactConfig(),
                self.SOURCE,
                display_calendar=self._calendar(phase),
            )
            for phase in (0.0, 0.3, 0.5, 0.7, 1.0)
        ]

        self.assertEqual(len({item.available_width for item in layouts}), 1)
        self.assertEqual(len({item.fitted_text for item in layouts}), 1)
        self.assertTrue(layouts[0].obstacles[0].limits_width)

    def test_editorial_only_limits_source_when_vertical_bands_intersect(self):
        config = self._config()
        nonintersecting = FunFactConfig(
            enabled=True,
            layout="editorial_floating",
            editorial_card_x=1200,
            editorial_card_y=200,
            editorial_card_width=600,
            editorial_card_height=300,
        )
        intersecting = replace(
            nonintersecting,
            editorial_card_y=900,
            editorial_card_height=160,
        )
        free = resolve_source_text_layout(config, nonintersecting, self.SOURCE)
        limited = resolve_source_text_layout(config, intersecting, self.SOURCE)

        self.assertFalse(free.obstacles[-1].limits_width)
        self.assertTrue(limited.obstacles[-1].limits_width)
        self.assertGreater(free.available_width, limited.available_width)

    def test_source_x_and_y_recompute_available_geometry(self):
        fact = FunFactConfig(
            enabled=True,
            layout="editorial_floating",
            editorial_card_x=1200,
            editorial_card_y=900,
            editorial_card_width=600,
            editorial_card_height=160,
        )
        left = resolve_source_text_layout(
            self._config(source_x=100, source_y=1020),
            fact,
            self.SOURCE,
        )
        right = resolve_source_text_layout(
            self._config(source_x=300, source_y=1020),
            fact,
            self.SOURCE,
        )
        above = resolve_source_text_layout(
            self._config(source_x=100, source_y=800),
            fact,
            self.SOURCE,
        )

        self.assertGreater(left.available_width, right.available_width)
        self.assertGreater(above.available_width, left.available_width)

    def test_unicode_bold_and_italic_use_real_font_metrics(self):
        config = self._config(
            source_font_weight="bold",
            source_font_style="italic",
        )
        text = "Source: análisis — Alpha · Beta: (2019–2026)"
        layout = resolve_source_text_layout(config, FunFactConfig(), text)

        self.assertEqual(layout.fitted_text, text)
        self.assertEqual(
            layout.full_text_width,
            measure_text_width(text, self._font(config)),
        )

    def test_scene_geometry_and_renderer_use_same_fitted_source(self):
        config = self._config(width=720, date_style="standard")
        scene = Scene(
            title="",
            time_label="2020",
            source_label=self.SOURCE * 2,
        )
        expected = resolve_source_text_layout(
            config,
            FunFactConfig(),
            scene.source_label,
            time_label=scene.time_label,
        )
        geometry = build_scene_geometry(config, FunFactConfig(), scene)
        renderer = BarRenderer(config=config)
        try:
            fitted = renderer._fit_source_label(scene.source_label, scene=scene)
        finally:
            renderer.close()

        self.assertEqual(fitted, expected.fitted_text)
        self.assertEqual(
            geometry["source_layout"]["fitted_text"],
            expected.fitted_text,
        )
        self.assertEqual(
            geometry["text_bounds"]["source"]["width"],
            expected.fitted_text_width,
        )

    def test_standard_and_short_layouts_respect_their_safe_right_edges(self):
        standard = self._config()
        short = apply_export_profile(standard, ExportConfig(mode="short"))
        for config in (standard, short):
            with self.subTest(size=(config.width, config.height)):
                layout = resolve_source_text_layout(
                    config,
                    FunFactConfig(),
                    self.SOURCE * 4,
                )
                self.assertLessEqual(
                    config.source_x + layout.fitted_text_width,
                    layout.safe_right,
                )
                self.assertLessEqual(layout.right_limit, layout.safe_right)


if __name__ == "__main__":
    unittest.main()
