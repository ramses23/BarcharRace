import unittest
from dataclasses import replace

import _test_path
from config.chart_config import ChartConfig
from core.bar_value_scale import BarValueScaleResolver, scale_bar_sprites
from core.logo_geometry import final_visual_bar_sprite
from models.bar_sprite import BarSprite


class LogoGrowthWithoutAxisTest(unittest.TestCase):
    def test_badge_grows_immediately_and_retains_full_width_endpoint(self):
        config = ChartConfig(value_grid_enabled=False, logo_size=100,
                             primary_logo_min_size=82, bar_logo_position='inside_right')
        bar = BarSprite('A', 0, '#123456', 20, 100, 0, 82,
                        logo_path='logo.png', bar_available_width=1000)
        widths = [final_visual_bar_sprite(config, replace(bar, width=w),
                                          primary_logo_available=True).width
                  for w in (0, .1, 1, 5, 20, 80, 82, 200, 999, 1000)]
        self.assertEqual(widths[0], 82)
        self.assertEqual(widths[-1], 1000)
        self.assertTrue(all(a < b for a, b in zip(widths, widths[1:])))

    def test_progressive_first_seventeen_periods_do_not_stay_at_logo_floor(self):
        config = ChartConfig(value_grid_enabled=False, start_bars_at_zero=True,
                             fps=60, steps_per_transition=380, logo_size=100,
                             primary_logo_min_size=82, bar_logo_position='inside_right')
        config = replace(config, animation=replace(config.animation, motion_mode='continuous'))
        base = BarSprite('A', 3, '#123456', 20, 100, 30, 82,
                         logo_path='logo.png', bar_available_width=1000)
        endpoints = [[replace(base, value=3 + i)] for i in range(77)]
        resolver = BarValueScaleResolver.from_config(config, endpoints)
        widths = []
        for period in (0, 1, 5, 10, 16, 17, 76):
            bars = endpoints[period]
            scale = resolver.for_sprites(bars, frame_index=period * 380)
            scaled = scale_bar_sprites(bars, scale)[0]
            widths.append(final_visual_bar_sprite(config, scaled, primary_logo_available=True).width)
        self.assertEqual(widths[0], 82)
        self.assertEqual(widths[-1], 1000)
        self.assertTrue(all(a < b for a, b in zip(widths, widths[1:])))

    def test_numeric_axes_missing_logos_and_outside_logos_are_unchanged(self):
        config = ChartConfig(value_grid_enabled=True, logo_size=100,
                             primary_logo_min_size=82, bar_logo_position='inside_right')
        base = BarSprite('A', 3, '#123456', 20, 100, 30, 82,
                         logo_path='logo.png', bar_available_width=1000)
        for mode in ('static', 'dynamic'):
            for width in (0, 30, 82, 150, 1000):
                bar = replace(base, width=width)
                visual = final_visual_bar_sprite(replace(config, value_grid_mode=mode), bar,
                                                 primary_logo_available=True)
                self.assertEqual(visual.width, max(82, width))
        for position in ('inside_right', 'outside_left', 'outside_right'):
            c = replace(config, value_grid_enabled=False, bar_logo_position=position)
            self.assertEqual(final_visual_bar_sprite(c, base).width, base.width)
            if position != 'inside_right':
                self.assertEqual(final_visual_bar_sprite(c, base, primary_logo_available=True).width,
                                 base.width)


if __name__ == '__main__':
    unittest.main()
