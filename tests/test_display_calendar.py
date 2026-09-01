import unittest
from datetime import datetime

import _test_path
import numpy as np
import pandas as pd
from matplotlib import font_manager

from config.chart_config import ChartConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from core.display_calendar import (
    DisplayCalendarError,
    DisplayCalendarResolver,
    parse_calendar_anchor,
)
from core.timeline import Timeline
from models.display_calendar import DisplayCalendarState, FlipModuleState
from models.scene import Scene
from renderer.bar_renderer import BarRenderer
from renderer.flip_calendar_renderer import FlipCalendarRenderer
from studio.layout_preview import build_studio_layout_preview
from studio.short_export import apply_export_profile


class DisplayCalendarResolverTest(unittest.TestCase):
    @staticmethod
    def _timeline(period_labels):
        rows = []
        for period, label in period_labels:
            rows.append({
                "period": period,
                "date": label,
                "name": "A",
                "value": period,
            })
        frame = pd.DataFrame(rows)
        return frame, Timeline(
            frame,
            DatasetConfig(
                year_column="period",
                name_column="name",
                value_column="value",
                time_label_column="date",
            ),
        )

    def test_parses_only_unambiguous_gregorian_anchors(self):
        self.assertEqual(parse_calendar_anchor("1950"), datetime(1950, 1, 1))
        self.assertEqual(parse_calendar_anchor("2001-02"), datetime(2001, 2, 1))
        self.assertEqual(
            parse_calendar_anchor("2023-06-02"), datetime(2023, 6, 2)
        )
        with self.assertRaises(DisplayCalendarError):
            parse_calendar_anchor("06/02/2023")
        with self.assertRaises(DisplayCalendarError):
            parse_calendar_anchor("2023-02-29")

    def test_annual_display_time_uses_real_calendar_without_new_rows(self):
        dataframe, timeline = self._timeline(((1, "1950"), (2, "1951"), (3, "1952")))
        original_rows = len(dataframe)
        resolver = DisplayCalendarResolver.from_timeline(
            timeline,
            timeline.get_years(),
            steps_per_transition=5,
        )

        self.assertEqual(resolver.frame_count, 10)
        self.assertEqual(resolver.state_at(0).display_date.isoformat(), "1950-01-01")
        self.assertEqual(resolver.state_at(2).display_date.isoformat(), "1950-07-02")
        self.assertEqual(resolver.state_at(4).display_date.isoformat(), "1951-01-01")
        self.assertEqual(len(dataframe), original_rows)

    def test_monthly_and_daily_anchors_use_exact_dates(self):
        _, monthly = self._timeline(
            ((1, "2001-01"), (2, "2001-02"), (3, "2001-03"))
        )
        monthly_resolver = DisplayCalendarResolver.from_timeline(
            monthly, monthly.get_years(), steps_per_transition=32
        )
        self.assertEqual(monthly_resolver.state_at(0).display_date.isoformat(), "2001-01-01")
        self.assertEqual(monthly_resolver.state_at(31).display_date.isoformat(), "2001-02-01")
        self.assertEqual(monthly_resolver.state_at(63).display_date.isoformat(), "2001-03-01")

        _, daily = self._timeline(
            ((1, "2023-06-01"), (2, "2023-06-02"), (3, "2023-06-03"))
        )
        daily_resolver = DisplayCalendarResolver.from_timeline(
            daily, daily.get_years(), steps_per_transition=5
        )
        self.assertEqual(daily_resolver.state_at(4).display_date.isoformat(), "2023-06-02")
        self.assertEqual(daily_resolver.state_at(9).display_date.isoformat(), "2023-06-03")

    def test_gregorian_leap_rules_are_preserved(self):
        _, leap = self._timeline(((1, "2000-02"), (2, "2000-03")))
        leap_resolver = DisplayCalendarResolver.from_timeline(
            leap, leap.get_years(), steps_per_transition=30
        )
        self.assertIn(
            "2000-02-29",
            {leap_resolver.state_at(index).display_date.isoformat() for index in range(30)},
        )

        _, common = self._timeline(((1, "1900-02"), (2, "1900-03")))
        common_resolver = DisplayCalendarResolver.from_timeline(
            common, common.get_years(), steps_per_transition=29
        )
        self.assertNotIn(
            "1900-02-29",
            {common_resolver.state_at(index).display_date.isoformat() for index in range(29)},
        )

    def test_year_boundary_changes_only_affected_modules(self):
        _, timeline = self._timeline(
            ((1, "2001-12-31"), (2, "2002-01-01"))
        )
        resolver = DisplayCalendarResolver.from_timeline(
            timeline, timeline.get_years(), steps_per_transition=5
        )
        state = resolver.state_at(3)

        self.assertEqual((state.year.old_value, state.year.new_value), ("2001", "2002"))
        self.assertEqual((state.month.old_value, state.month.new_value), ("DEC", "JAN"))
        self.assertEqual((state.day.old_value, state.day.new_value), ("31", "1"))
        self.assertFalse(resolver.state_at(4).day.is_flipping)

    def test_month_boundary_keeps_year_module_stable(self):
        _, timeline = self._timeline(
            ((1, "2001-01-31"), (2, "2001-02-01"))
        )
        state = DisplayCalendarResolver.from_timeline(
            timeline, timeline.get_years(), steps_per_transition=5
        ).state_at(3)

        self.assertEqual((state.month.old_value, state.month.new_value), ("JAN", "FEB"))
        self.assertEqual((state.day.old_value, state.day.new_value), ("31", "1"))
        self.assertFalse(state.year.is_flipping)

    def test_frame_skips_are_direct_and_do_not_expand_frame_count(self):
        _, timeline = self._timeline(((1, "2001"), (2, "2002")))
        resolver = DisplayCalendarResolver.from_timeline(
            timeline, timeline.get_years(), steps_per_transition=3
        )
        first, second = resolver.state_at(0), resolver.state_at(1)

        self.assertEqual(resolver.frame_count, 3)
        self.assertGreater((second.display_date - first.display_date).days, 1)
        self.assertEqual(second.day.old_value, str(first.display_date.day))
        self.assertNotEqual(second.day.old_value, second.day.new_value)

    def test_random_access_is_deterministic_and_continuous_count_matches(self):
        _, timeline = self._timeline(((1, "2000"), (2, "2001"), (3, "2002")))
        resolver = DisplayCalendarResolver.from_timeline(
            timeline,
            timeline.get_years(),
            steps_per_transition=8,
            continuous_motion=True,
        )
        direct = resolver.state_at(9)
        _ = [resolver.state_at(index) for index in range(9)]

        self.assertEqual(resolver.frame_count, 17)
        self.assertEqual(direct, resolver.state_at(9))

    def test_random_access_frame_500_needs_no_prior_renderer_state(self):
        _, timeline = self._timeline(((1, "2000"), (2, "2010")))
        resolver = DisplayCalendarResolver.from_timeline(
            timeline,
            timeline.get_years(),
            steps_per_transition=601,
        )

        direct = resolver.state_at(500)
        neighbors = tuple(resolver.state_at(index) for index in (499, 500, 501))

        self.assertEqual(direct, neighbors[1])
        self.assertEqual(direct.frame_index, 500)

    def test_rank_movement_duration_does_not_change_calendar_progression(self):
        dataframe = pd.DataFrame({
            "year": [1950, 1951],
            "country": ["A", "A"],
            "value": [10, 20],
        })
        base = {
            "chart": {
                "date_style": "flip_calendar",
                "steps_per_transition": 11,
                "logos_enabled": False,
            },
            "selection": {"top_n": 1},
        }
        states = []
        for duration in (0.5, 0.7, 1.0):
            project = {
                **base,
                "animation": {"rank_movement_duration": duration},
            }
            states.append(build_studio_layout_preview(
                project,
                dataframe,
                {
                    "preview_mode": "transition",
                    "year": 1950,
                    "transition_progress": 0.5,
                },
            ).scene.display_calendar)
        self.assertEqual(states[0], states[1])
        self.assertEqual(states[1], states[2])


class FlipCalendarRendererTest(unittest.TestCase):
    @staticmethod
    def _state(phase):
        return DisplayCalendarState(
            display_datetime=datetime(2023, 6, 2),
            display_date=datetime(2023, 6, 2).date(),
            year=FlipModuleState("2023", "2023", 1.0),
            month=FlipModuleState("MAY", "JUN", phase),
            day=FlipModuleState("1", "2", phase),
            frame_index=10,
        )

    @staticmethod
    def _image(*, phase=1.0, **config_values):
        config = ChartConfig(date_style="flip_calendar", **config_values)
        return FlipCalendarRenderer().command(
            FlipCalendarRendererTest._state(phase),
            config,
            font_path=font_manager.findfont("DejaVu Sans"),
        )[0]

    @staticmethod
    def _alpha_at(image, x, pil_y):
        return int(image[image.shape[0] - 1 - pil_y, x, 3])

    def test_renderer_is_deterministic_and_has_finished_geometry(self):
        config = ChartConfig(
            width=640,
            height=360,
            date_style="flip_calendar",
            time_label_x=620,
            time_label_y=190,
            time_label_opacity=0.8,
        )
        font_path = font_manager.findfont("DejaVu Sans")
        renderer = FlipCalendarRenderer()

        command_a = renderer.command(self._state(0.5), config, font_path=font_path)
        command_b = renderer.command(self._state(0.5), config, font_path=font_path)
        image, left, top = command_a

        self.assertTrue(np.array_equal(command_a[0], command_b[0]))
        self.assertEqual(image.shape, (236, 360, 4))
        self.assertEqual((left, top), (260, 72))
        self.assertGreater(np.count_nonzero(image[:, :, 3]), 10000)

    def test_flip_phases_change_mechanical_halves(self):
        config = ChartConfig(date_style="flip_calendar")
        font_path = font_manager.findfont("DejaVu Sans")
        renderer = FlipCalendarRenderer()
        images = [
            renderer.command(self._state(phase), config, font_path=font_path)[0]
            for phase in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]
        self.assertTrue(all(
            not np.array_equal(first, second)
            for first, second in zip(images, images[1:])
        ))

    def test_standard_and_short_positions_keep_calendar_on_canvas(self):
        font_path = font_manager.findfont("DejaVu Sans")
        renderer = FlipCalendarRenderer()
        standard = ChartConfig(date_style="flip_calendar")
        short = apply_export_profile(
            standard,
            ExportConfig(mode="short"),
        )
        for config in (standard, short):
            image, left, top = renderer.command(
                self._state(1.0), config, font_path=font_path
            )
            self.assertGreaterEqual(left, 0)
            self.assertGreaterEqual(top, 0)
            self.assertLessEqual(left + image.shape[1], config.width)
            self.assertLessEqual(top + image.shape[0], config.height)

    def test_date_opacity_controls_whole_calendar(self):
        font_path = font_manager.findfont("DejaVu Sans")
        renderer = FlipCalendarRenderer()
        opaque = renderer.command(
            self._state(1.0),
            ChartConfig(date_style="flip_calendar", time_label_opacity=1.0),
            font_path=font_path,
        )[0]
        half = renderer.command(
            self._state(1.0),
            ChartConfig(date_style="flip_calendar", time_label_opacity=0.5),
            font_path=font_path,
        )[0]
        self.assertLess(np.max(half[:, :, 3]), np.max(opaque[:, :, 3]))

    def test_card_opacity_controls_only_each_module_fill(self):
        fill_points = ((180, 30), (80, 140), (250, 140))
        expected_alpha = {
            1.0: 255,
            0.75: 191,
            0.5: 128,
            0.25: 64,
            0.0: 0,
        }
        for opacity, expected in expected_alpha.items():
            with self.subTest(opacity=opacity):
                image = self._image(
                    flip_calendar_card_opacity=opacity,
                    time_label_opacity=1.0,
                )
                self.assertEqual(
                    [self._alpha_at(image, *point) for point in fill_points],
                    [expected, expected, expected],
                )
                self.assertEqual(np.max(image[:, :, 3]), 255)

    def test_card_and_global_date_opacity_compose_multiplicatively(self):
        half_card = self._image(
            flip_calendar_card_opacity=0.5,
            time_label_opacity=1.0,
        )
        half_both = self._image(
            flip_calendar_card_opacity=0.5,
            time_label_opacity=0.5,
        )
        hidden_date = self._image(
            flip_calendar_card_opacity=1.0,
            time_label_opacity=0.0,
        )

        self.assertEqual(self._alpha_at(half_card, 180, 30), 128)
        self.assertEqual(self._alpha_at(half_both, 180, 30), 64)
        self.assertFalse(np.any(hidden_date[:, :, 3]))
        self.assertTrue(np.array_equal(
            half_both[:, :, 3],
            np.uint8(half_card[:, :, 3].astype(np.float32) * 0.5),
        ))

    def test_zero_card_opacity_preserves_text_border_hinges_seam_and_shadow(self):
        image = self._image(
            flip_calendar_card_opacity=0.0,
            flip_calendar_shadow_opacity=0.32,
            time_label_opacity=1.0,
        )
        pil_alpha = image[::-1, :, 3]

        self.assertEqual(self._alpha_at(image, 180, 30), 0)
        self.assertEqual(np.max(pil_alpha[20:100, 40:320]), 255)  # value text
        self.assertGreater(np.max(pil_alpha[45:58, 0:355]), 0)  # seam/hinges
        self.assertGreater(np.max(pil_alpha[0:105, 0:10]), 0)  # border
        self.assertEqual(self._alpha_at(image, 355, 100), 84)  # shadow only

    def test_shadow_opacity_is_independent_before_global_date_opacity(self):
        no_shadow = self._image(
            flip_calendar_card_opacity=0.0,
            flip_calendar_shadow_opacity=0.0,
            time_label_opacity=1.0,
        )
        full_shadow = self._image(
            flip_calendar_card_opacity=0.0,
            flip_calendar_shadow_opacity=1.0,
            time_label_opacity=1.0,
        )
        half_date = self._image(
            flip_calendar_card_opacity=0.0,
            flip_calendar_shadow_opacity=1.0,
            time_label_opacity=0.5,
        )

        self.assertEqual(self._alpha_at(no_shadow, 355, 100), 0)
        self.assertEqual(self._alpha_at(full_shadow, 355, 100), 255)
        self.assertEqual(self._alpha_at(half_date, 355, 100), 127)

    def test_card_opacity_is_used_during_settled_and_mid_flip_phases(self):
        for phase in (0.5, 1.0):
            with self.subTest(phase=phase):
                image = self._image(
                    phase=phase,
                    flip_calendar_card_opacity=0.25,
                    time_label_opacity=1.0,
                )
                self.assertEqual(self._alpha_at(image, 180, 30), 64)
                self.assertEqual(self._alpha_at(image, 80, 140), 64)
                self.assertEqual(self._alpha_at(image, 250, 140), 64)

    def test_card_opacity_participates_in_raster_cache_key(self):
        font_path = font_manager.findfont("DejaVu Sans")
        renderer = FlipCalendarRenderer()
        opaque_config = ChartConfig(
            date_style="flip_calendar",
            flip_calendar_card_opacity=1.0,
        )
        transparent_config = ChartConfig(
            date_style="flip_calendar",
            flip_calendar_card_opacity=0.0,
        )

        opaque_first = renderer.command(
            self._state(1.0), opaque_config, font_path=font_path
        )[0]
        transparent = renderer.command(
            self._state(1.0), transparent_config, font_path=font_path
        )[0]
        opaque_again = renderer.command(
            self._state(1.0), opaque_config, font_path=font_path
        )[0]

        self.assertFalse(np.array_equal(opaque_first, transparent))
        self.assertTrue(np.array_equal(opaque_first, opaque_again))
        self.assertEqual(len(renderer._cache), 2)

    def test_standard_date_ignores_calendar_state_pixel_for_pixel(self):
        config = ChartConfig(
            width=640,
            height=360,
            date_style="standard",
            time_label_x=600,
            time_label_y=300,
            time_label_font_size=48,
        )
        renderer = BarRenderer(output_dir=".", config=config)
        try:
            plain = np.frombuffer(
                renderer.render_rgba(Scene(title="", time_label="2023")),
                dtype=np.uint8,
            ).copy()
            with_state = np.frombuffer(
                renderer.render_rgba(Scene(
                    title="",
                    time_label="2023",
                    display_calendar=self._state(0.5),
                )),
                dtype=np.uint8,
            ).copy()
        finally:
            renderer.close()
        self.assertTrue(np.array_equal(plain, with_state))

    def test_standard_date_ignores_flip_card_opacity_pixel_for_pixel(self):
        images = []
        for card_opacity in (0.0, 1.0):
            config = ChartConfig(
                width=640,
                height=360,
                date_style="standard",
                flip_calendar_card_opacity=card_opacity,
                time_label_x=600,
                time_label_y=300,
                time_label_font_size=48,
            )
            renderer = BarRenderer(output_dir=".", config=config)
            try:
                images.append(np.frombuffer(
                    renderer.render_rgba(Scene(title="", time_label="2023")),
                    dtype=np.uint8,
                ).copy())
            finally:
                renderer.close()
        self.assertTrue(np.array_equal(*images))


if __name__ == "__main__":
    unittest.main()
