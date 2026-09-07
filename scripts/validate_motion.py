"""Reproducible partial-render motion diagnostic; all artifacts stay outside the app."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config.animation_config import AnimationConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.export_config import ExportConfig
from pipeline.render_job import RenderJob
from renderer.bar_renderer import BarRenderer
from renderer.subpixel import rasterize_image_command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--secondary", type=Path, required=True)
    parser.add_argument("--material", action="store_true")
    parser.add_argument("--gradient", action="store_true")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError("Validation artifacts must be outside the repository.")
    out.mkdir(parents=True, exist_ok=True)
    rows = []

    class DiagnosticRenderer(BarRenderer):
        def render_rgba(self, scene):
            pixels = super().render_rgba(scene)
            if scene.frame_index in range(60, 73) or scene.frame_index in range(123, 130):
                bars = []
                for sprite in scene.bars:
                    visual, _ = self._final_visual_geometry(sprite)
                    logos = []
                    for slot, path, layout, _ in self._logo_layouts_for_sprite(visual):
                        command = self._logo_composite_command(visual, slot=slot, logo_path=path, layout=layout)
                        raster = rasterize_image_command(command) if command else None
                        logos.append({"slot": slot, "layout": layout,
                            "command_xy": list(command[1:]) if command else None,
                            "raster_xy": list(raster[1:]) if raster else None,
                            "fractional_scale": getattr(command, "scale", 1),
                            "raster_size": list(command[0].shape[:2]) if command else None})
                    bars.append({"name": sprite.name,
                        "logical_rect": [sprite.x, sprite.y, sprite.width, sprite.height],
                        "visual_rect": [visual.x, visual.y, visual.width, visual.height],
                        "logos": logos,
                        "text_xy": [list(c[1:]) for c in self._bar_text_commands(visual)],
                        "body_snap": (self._bar_artists[0].bar.get_snap()
                            if self._bar_artists[0].bar is not None else False),
                    })
                rows.append({"global_frame": scene.frame_index, "bars": bars,
                    "axis": asdict(scene.value_axis),
                    "grid_snap": self._value_grid_collection.get_snap(),
                    "tick_positions": [list(a.get_position()) for a in self._value_tick_artists if a.get_visible()],
                    "tick_compositor_xy": [list(c[1:]) for c in self._value_tick_composite_artist.commands],
                })
            if scene.frame_index == 126:
                from PIL import Image
                Image.frombytes("RGBA", (self.config.width, self.config.height), pixels).save(out / f"{args.label}.png")
            return pixels

    config = ChartConfig(
        width=960, height=540, dpi=100, left_margin=180, right_margin=80,
        top_margin=150, bottom_margin=80, bar_height=62, bar_gap=30,
        fps=60, steps_per_transition=360, frame_output_mode="ffmpeg_stream",
        frames_dir=str(out / "frames"), output_file=str(out / f"{args.label}.mp4"),
        title="Motion validation", title_x=40, title_y=35, title_font_size=22,
        subtitle_enabled=False, source_label_enabled=False, time_label_enabled=False,
        animation=AnimationConfig(motion_mode="continuous", easing="ease_out_cubic", rank_movement_duration=0.7),
        bar_appearance_mode="unified", bar_fill_type="gradient" if args.gradient else "solid",
        bar_gradient_enabled=args.gradient,
        bar_texture_enabled=args.material, bar_texture_intensity=0.1,
        bar_shadow_enabled=False, bar_logo_position="inside_left", logo_size=100,
        bar_secondary_logo_enabled=True, bar_secondary_logo_layout="side_by_side",
        bar_secondary_logo_position="inside_right", bar_secondary_logo_size=26,
        value_grid_enabled=True, value_grid_mode="dynamic", value_grid_line_opacity=0.65,
        value_grid_tick_font_size=16, label_font_size=18, value_font_size=18,
    )
    names = ("USA", "Mexico", "Canada")
    dataset = DatasetConfig(
        category_logos={name: str(args.primary.resolve()) for name in names},
        category_secondary_logos={name: str(args.secondary.resolve()) for name in names},
    )
    with patch("pipeline.render_job.BarRenderer", DiagnosticRenderer):
        result = RenderJob(config=config, dataset_config=dataset,
            data_source_config=DataSourceConfig(source_type="csv", csv_path=str(ROOT / "data/datasets/sample_dynamic.csv")),
            export_config=ExportConfig(render_start_frame=60, render_end_frame=420),
            project_root=out,
        ).run()
    report = {"frames": result.frames_rendered, "clip": result.output_file,
        "draw_ms_per_frame": result.profile.draw_frames_seconds * 1000 / result.frames_rendered,
        "profile": asdict(result.profile), "samples": rows}
    (out / f"{args.label}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2))


if __name__ == "__main__":
    main()
