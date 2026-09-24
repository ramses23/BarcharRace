import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import _test_path
from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.export_config import ExportConfig
from config.project_file_loader import ProjectFileError, load_project_data, load_project_file
from core.bar_value_scale import BarValueScaleResolver
from core.rank_celebration import RankCelebrationTimeline, celebration_particles
from models.bar_sprite import BarSprite
from models.scene import Scene
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from studio.preview import render_project_preview
from studio.project_builder import project_form_values, save_project_data


NAMES = ("A", "B", "C", "D", "E")


def sprites(values):
    ordered = sorted(values, key=lambda name: (-values[name], name))
    return tuple(BarSprite(name=name, value=values[name], color="#336699",
                           x=20, y=40 + rank * 50, width=100, height=40,
                           rank=rank + 1) for rank, name in enumerate(ordered))


def timeline(rows, mode="podium", duration=.4, timing="uniform"):
    config = ChartConfig(width=360, height=260, fps=30, steps_per_transition=90,
        rank_celebration=mode, animation=AnimationConfig(
            rank_movement_duration=duration, transition_duration_mode=timing))
    resolver = BarValueScaleResolver.from_config(config, tuple(sprites(row) for row in rows))
    return resolver.rank_celebration_timeline, resolver


BASE = {"A": 50, "B": 40, "C": 30, "D": 20, "E": 10}
BRONZE = {"A": 50, "B": 40, "D": 35, "C": 30, "E": 10}


class RankCelebrationTest(unittest.TestCase):
    def test_promotions_only_final_attained_rank(self):
        for target, expected in (
            ({"A": 50, "B": 40, "D": 35, "C": 30, "E": 10}, 3),
            ({"A": 50, "B": 40, "E": 35, "C": 30, "D": 20}, 3),
            ({"A": 50, "C": 45, "B": 40, "D": 20, "E": 10}, 2),
            ({"A": 50, "E": 45, "B": 40, "C": 30, "D": 20}, 2),
            ({"B": 55, "A": 50, "C": 30, "D": 20, "E": 10}, 1),
            ({"D": 60, "A": 50, "B": 40, "C": 30, "E": 10}, 1),
        ):
            with self.subTest(expected=expected, target=target):
                result, _ = timeline((BASE, target))
                self.assertEqual([(event.name, event.rank) for event in result.events],
                                 [("E" if target["E"] > BASE["E"] else
                                   "D" if target["D"] > BASE["D"] else
                                   "C" if target["C"] > BASE["C"] else "B", expected)])
                self.assertGreater(result.events[0].frame, 0)
                self.assertGreaterEqual(result.events[0].frame, 35)

    def test_crossing_triggers_at_first_visually_attained_slot(self):
        for target, name, rank in (
            ({"A": 50, "B": 40, "D": 35, "C": 30, "E": 10}, "D", 3),
            ({"A": 50, "C": 45, "B": 40, "D": 20, "E": 10}, "C", 2),
            ({"B": 55, "A": 50, "C": 30, "D": 20, "E": 10}, "B", 1),
        ):
            with self.subTest(rank=rank):
                result, _ = timeline((BASE, target), duration=1.0)
                self.assertEqual([(e.name, e.rank) for e in result.events], [(name, rank)])
                event = result.events[0]
                self.assertLess(event.frame, result.plan.frame_bounds(0)[1] - 1)
                first_visual_slot = next(frame for frame in range(1, event.frame + 1)
                    if result.display_timeline._targets(frame)[0].get(name) == rank - 1
                    and abs(dict(result.display_timeline.at(frame)[0])[name]
                            - (rank - 1)) <= .035)
                self.assertEqual(event.frame, first_visual_slot)

    def test_nearby_distinct_promotions_are_not_globally_suppressed(self):
        end = {"A": 50, "B": 40, "C": 30, "D": 95, "E": 92}
        result, resolver = timeline((BASE, end), duration=1.0)
        self.assertEqual([(e.name, e.rank) for e in result.events],
                         [("D", 1), ("E", 2)])
        self.assertLess(result.events[1].frame - result.events[0].frame, 10)
        self.assertEqual(len(set(result.events)), len(result.events))
        for event in result.events:
            self.assertEqual(resolver.celebrations_at(event.frame)[-1].age_frames, 0)

    def test_descent_stable_tie_and_initial_podium_do_not_celebrate(self):
        for rows in ((BASE, BASE),
                     (BASE, {"A": 40, "B": 50, "C": 30, "D": 20, "E": 10}),
                     (BASE, {"A": 50, "B": 40, "C": 30, "D": 30, "E": 10})):
            with self.subTest(rows=rows):
                result, resolver = timeline(rows)
                # A descent can coexist with somebody else's true ascent.
                self.assertFalse(any(event.name == "A" and event.rank == 2 for event in result.events))
                self.assertFalse(any(event.name == "D" for event in result.events))
                self.assertEqual(resolver.celebrations_at(0), ())

    def test_recovery_can_celebrate_again(self):
        rows = (BASE, {"B": 55, "A": 50, "C": 30, "D": 20, "E": 10},
                {"A": 60, "B": 55, "C": 30, "D": 20, "E": 10})
        result, _ = timeline(rows)
        self.assertEqual([(event.name, event.rank) for event in result.events],
                         [("B", 1), ("A", 1)])

    def test_bronze_rearms_after_departure_then_progresses_to_silver_and_gold(self):
        silver = {"A": 50, "D": 45, "B": 40, "C": 30, "E": 10}
        gold = {"D": 60, "A": 50, "B": 40, "C": 30, "E": 10}
        result, resolver = timeline((BASE, BRONZE, BASE, BRONZE, BRONZE, silver, gold))
        events = [event for event in result.events if event.name == "D"]
        self.assertEqual([event.rank for event in events], [3, 3, 2, 1])
        self.assertEqual([result.plan.locate(event.frame)[0] for event in events],
                         [0, 2, 4, 5])
        self.assertEqual(len({event.frame for event in events}), 4)
        for event in events:
            self.assertEqual(resolver.celebrations_at(event.frame)[-1].age_frames, 0)

    def test_rearm_uses_clear_departure_before_the_immediate_previous_frame(self):
        result, _ = timeline((BASE, BRONZE, BASE, BRONZE))
        second_start, second_end = result.plan.frame_bounds(2)
        crossing = next(frame for frame in range(second_start, second_end)
            if result.display_timeline._targets(frame)[0]["D"] == 2)
        original_at = result.display_timeline.at

        def near_slot_on_previous_frame(frame):
            ranks, ticks = original_at(frame)
            if frame == crossing - 1:
                ranks = tuple((name, 2.01 if name == "D" else rank)
                              for name, rank in ranks)
            return ranks, ticks

        with patch.object(result.display_timeline, "at", side_effect=near_slot_on_previous_frame):
            rebuilt = RankCelebrationTimeline(
                result.config, result.sprite_sets, result.display_timeline)
        self.assertEqual([event.rank for event in rebuilt.events if event.name == "D"], [3, 3])

    def test_small_visual_oscillation_does_not_rearm_bronze(self):
        result, _ = timeline((BASE, BRONZE, BASE, BRONZE))
        first_bronze = next(event for event in result.events if event.name == "D")
        original_at = result.display_timeline.at

        def near_slot_without_departure(frame):
            ranks, ticks = original_at(frame)
            if frame > first_bronze.frame:
                ranks = tuple((name, 2.01 if frame % 2 else 1.99) if name == "D"
                              else (name, rank) for name, rank in ranks)
            return ranks, ticks

        with patch.object(result.display_timeline, "at", side_effect=near_slot_without_departure):
            rebuilt = RankCelebrationTimeline(
                result.config, result.sprite_sets, result.display_timeline)
        self.assertEqual([event.rank for event in rebuilt.events if event.name == "D"], [3])

    def test_activity_weighted_keeps_completion_on_its_global_timeline(self):
        end = {"D": 60, "A": 50, "B": 40, "C": 30, "E": 10}
        result, resolver = timeline((BASE, end), timing="activity_weighted")
        self.assertEqual(len(result.events), 1)
        event = result.events[0]
        self.assertGreaterEqual(event.frame, result.plan.frame_at_progress(0, .4))
        self.assertEqual(resolver.celebrations_at(event.frame)[0].age_frames, 0)

    def test_mode_filters(self):
        bronze = {"A": 50, "B": 40, "D": 35, "C": 30, "E": 10}
        silver = {"A": 50, "D": 45, "B": 40, "C": 30, "E": 10}
        gold = {"D": 60, "A": 50, "B": 40, "C": 30, "E": 10}
        for mode, expected in (("off", ()), ("first", (1,)),
                               ("top_two", (2, 1)), ("podium", (3, 2, 1))):
            with self.subTest(mode=mode):
                result, _ = timeline((BASE, bronze, silver, gold), mode)
                self.assertEqual(tuple(event.rank for event in result.events) if result else (), expected)

    def test_random_access_particles_and_anchor_are_deterministic(self):
        rows = (BASE, {"D": 60, "A": 50, "B": 40, "C": 30, "E": 10})
        result, resolver = timeline(rows)
        event = result.events[0]
        frame = event.frame + 5
        first = resolver.celebrations_at(frame)
        resolver.celebrations_at(frame + 10)
        resolver.celebrations_at(0)
        second = resolver.celebrations_at(frame)
        fresh = timeline(rows)[1].celebrations_at(frame)
        self.assertEqual(first, second)
        self.assertEqual(first, fresh)
        self.assertEqual(celebration_particles(event, 5, 30, (100, 100)),
                         celebration_particles(event, 5, 30, (100, 100)))
        self.assertEqual(resolver.celebrations_at(event.frame - 1), ())
        self.assertEqual(resolver.celebrations_at(event.frame + 30), ())

    def test_config_default_round_trip_and_invalid(self):
        self.assertEqual(load_project_data({}).chart_config.rank_celebration, "off")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            save_project_data({"chart": {"rank_celebration": "podium"}}, path)
            self.assertEqual(load_project_file(path).chart_config.rank_celebration, "podium")
        self.assertEqual(project_form_values({"chart": {"rank_celebration": "top_two"}})["rank_celebration"], "top_two")
        with self.assertRaises(ProjectFileError):
            load_project_data({"chart": {"rank_celebration": "invalid"}})

    def test_studio_control_writes_chart_configuration(self):
        from streamlit.testing.v1 import AppTest
        app_path = Path(__file__).resolve().parents[1] / "src/ui/project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        section = next(control for control in app.get("button_group")
                       if control.label == "Editor section")
        section.set_value("Export")
        app.run()
        control = next(control for control in app.get("button_group")
                       if control.label == "Rank Celebration")
        control.set_value("podium")
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(json.loads(app.json[0].value)["chart"]["rank_celebration"],
                         "podium")

    def test_renderer_draws_event_at_frozen_visual_origin(self):
        rows = (BASE, {"D": 60, "A": 50, "B": 40, "C": 30, "E": 10})
        result, resolver = timeline(rows)
        active = resolver.celebrations_at(result.events[0].frame + 2)
        renderer = BarRenderer(output_dir=None, config=result.config)
        try:
            renderer.render_rgba(Scene(title="", rank_celebrations=active))
            self.assertEqual(len(renderer._rank_celebration_artist.get_offsets()), 17)
            self.assertEqual(len(renderer._rank_celebration_glints.get_offsets()), 3)
            renderer.render_rgba(Scene(title=""))
            self.assertEqual(len(renderer._rank_celebration_artist.get_offsets()), 0)
        finally:
            renderer.close()

    def test_origin_uses_resolved_primary_logo_or_visual_bar_end(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            logo = Path(directory) / "logo.png"
            Image.new("RGBA", (16, 16), "white").save(logo)
            config = ChartConfig(width=360, height=260, bar_logo_position="inside_right",
                                 rank_celebration="podium")
            renderer = BarRenderer(output_dir=None, config=config)
            try:
                sprite = replace(sprites(BASE)[0], logo_path=str(logo), width=120)
                visual, _ = renderer._final_visual_geometry(sprite)
                layout = renderer._logo_layout(visual)
                self.assertEqual(renderer._rank_celebration_origin(sprite),
                    ((layout["left"] + layout["right"]) / 2,
                     (layout["top"] + layout["bottom"]) / 2))
                plain = replace(sprite, logo_path=None)
                resolved, _ = renderer._final_visual_geometry(plain)
                self.assertEqual(renderer._rank_celebration_origin(plain),
                                 (resolved.x + resolved.width, resolved.y))
            finally:
                renderer.close()

    def test_custom_window_and_review_share_global_events(self):
        with tempfile.TemporaryDirectory() as directory:
            csv = Path(directory) / "data.csv"
            csv.write_text("year,country,value\n0,A,50\n0,B,40\n0,C,30\n0,D,20\n1,A,50\n1,B,40\n1,C,30\n1,D,60\n", encoding="utf-8")
            config = ChartConfig(fps=30, steps_per_transition=90, rank_celebration="podium",
                animation=AnimationConfig(rank_movement_duration=.4))
            source = DataSourceConfig(csv_path=str(csv))

            def sample(export, frames):
                scenes = []
                with patch("pipeline.render_job.BarRenderer"), patch("builtins.print"):
                    RenderJob(config=config, data_source_config=source, export_config=export).run(
                        frame_sampler=lambda start, end: tuple(f for f in frames if start <= f < end),
                        frame_consumer=lambda scene, renderer: scenes.append(scene))
                return scenes

            frames = (0, 35, 50, 60, 70)
            full = sample(ExportConfig(), frames)
            clip = sample(ExportConfig(render_start_frame=35, render_end_frame=71), frames)
            self.assertEqual(clip, full[1:])
            self.assertTrue(any(scene.rank_celebrations for scene in full))
            for review in ("quick", "motion"):
                with self.subTest(review=review):
                    self.assertEqual(sample(ExportConfig(review_mode=review), frames), full)
            self.assertTrue(any(scene.rank_celebrations for scene in
                sample(ExportConfig(mode="short"), frames)))
            active_scene = next(scene for scene in full if scene.rank_celebrations)
            project = {
                "chart": {"fps": 30, "steps_per_transition": 90,
                          "rank_celebration": "podium"},
                "animation": {"rank_movement_duration": .4},
                "data_source": {"csv_path": str(csv)},
            }
            with patch("studio.preview.BarRenderer") as renderer:
                render_project_preview("preview", root_dir=Path(directory),
                    project_data=project, year=0, preview_mode="transition",
                    transition_progress=active_scene.frame_index / 89)
                preview = renderer.return_value.render.call_args.args[0]
            self.assertEqual(preview.frame_index, active_scene.frame_index)
            self.assertEqual(preview.rank_celebrations, active_scene.rank_celebrations)


if __name__ == "__main__":
    unittest.main()
