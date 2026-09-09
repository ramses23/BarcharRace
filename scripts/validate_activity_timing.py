"""External sentinel report and optional early-years clip; source project stays untouched."""

import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config.project_file_loader import load_project_file
from core.bar_selector import BarSelector
from core.layout_engine import LayoutEngine
from core.timeline import Timeline
from core.transition_timing import build_transition_timing_plan, timing_plan_from_timeline, allocation_weight
from importers.data_source_loader import DataSourceLoader
from pipeline.render_job import RenderJob
from studio.fun_fact_layout import apply_fun_fact_layout
from studio.project_runtime import resolve_project_preset_paths
from studio.short_export import apply_export_profile, resolve_export_periods, short_fun_fact_config
from validators.dataset_validator import DatasetValidator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--compare-report", type=Path, help="Previously generated linear allocation report.")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("Validation output must be outside the repository.")
    output.mkdir(parents=True, exist_ok=True)
    preset = resolve_project_preset_paths(load_project_file(args.project), project_root=args.project_root)
    csv = Path(preset.data_source_config.csv_path)
    before = {str(p): sha256(p.read_bytes()).hexdigest() for p in (args.project, csv)}
    dataframe = DatasetValidator(preset.dataset_config).validate(DataSourceLoader(preset.data_source_config).load())
    timeline = Timeline(dataframe, preset.dataset_config)
    years = resolve_export_periods(timeline.get_years(), preset.export_config)
    facts = short_fun_fact_config(preset.fun_fact_config, preset.export_config)
    chart = apply_fun_fact_layout(apply_export_profile(preset.chart_config, preset.export_config), facts)
    chart = replace(chart, animation=replace(chart.animation,
        transition_duration_mode="activity_weighted", minimum_transition_duration_seconds=1.0))
    selector, layout = BarSelector(chart.selection), LayoutEngine(chart, facts)
    endpoints = tuple(layout.build(selector.select(timeline.get_frame(year))) for year in years)
    timings = []
    for _ in range(30):
        started = perf_counter()
        plan = build_transition_timing_plan(chart, endpoints)
        timings.append(perf_counter() - started)
    assert plan == timing_plan_from_timeline(chart, timeline, years)
    assert plan.total_transition_frames == (len(years) - 1) * chart.steps_per_transition
    started = perf_counter()
    for i in range(100000):
        plan.locate((i * 7919) % plan.frame_count)
    lookup = (perf_counter() - started) / 100000
    rows = []
    previous = json.loads(args.compare_report.read_text(encoding="utf-8")) if args.compare_report else None
    previous_rows = {row["transition"]: row for row in previous["rows"]} if previous else {}
    pacing = {label: {"uniform_frames": 0, "weighted_frames": 0} for label in ("0", "1", "2+")}
    for i, activity in enumerate(plan.activities):
        uniform = chart.steps_per_transition
        weighted = plan.steps_per_transition[i]
        rows.append({"transition": f"{timeline.get_time_label(years[i])} -> {timeline.get_time_label(years[i + 1])}",
            **asdict(activity), "allocation_weight": allocation_weight(activity.score),
            "uniform_frames": uniform, "weighted_frames": weighted,
            "weighted_seconds": weighted / chart.fps})
        if previous:
            old = previous_rows[rows[-1]["transition"]]
            assert old["score"] == activity.score, "Activity score changed from baseline."
            rows[-1]["old_linear_frames"] = old["weighted_frames"]
        label = str(activity.changed_bars) if activity.changed_bars < 2 else "2+"
        extra = int(i == 0 and chart.animation.continuous_motion)
        pacing[label]["uniform_frames"] += uniform + extra
        pacing[label]["weighted_frames"] += weighted + extra
    for bucket in pacing.values():
        for mode in ("uniform", "weighted"):
            bucket[mode + "_seconds"] = bucket[mode + "_frames"] / chart.fps
            bucket[mode + "_percent"] = 100 * bucket[mode + "_frames"] / plan.frame_count
    report = {"project": preset.name, "fps": chart.fps, "rows": rows, "pacing": pacing,
        "transition_frames": plan.total_transition_frames, "total_frames": plan.frame_count,
        "duration_seconds": plan.frame_count / chart.fps,
        "plan_build_median_ms": median(timings) * 1000, "lookup_microseconds": lookup * 1e6}
    def duration_stats(values):
        return {"min": min(values), "median": median(values), "max": max(values)} if values else {}
    report["positive_duration_seconds"] = duration_stats([
        row["weighted_seconds"] for row in rows if row["score"] > 0])
    if previous:
        assert previous["total_frames"] == plan.frame_count
        report["old_linear_pacing"] = previous["pacing"]
        report["old_linear_positive_duration_seconds"] = duration_stats([
            row["weighted_seconds"] for row in previous["rows"] if row["score"] > 0])
    if args.render:
        end = plan.prefix_offsets[min(4, len(years) - 1)] + int(plan.continuous_motion)
        export = replace(preset.export_config, render_start_frame=0, render_end_frame=end)
        clip_chart = replace(preset.chart_config, animation=chart.animation,
            frame_output_mode="ffmpeg_stream", output_file=str(output / "activity_weighted_early_years.mp4"),
            frames_dir=str(output / "frames"))
        last_update = [0.0]
        def progress(event):
            now = perf_counter()
            if event.stage != "render_frames" or now - last_update[0] > 15:
                print(f"{event.stage}: {event.current}/{event.total} {event.message}", flush=True)
                last_update[0] = now
        result = RenderJob(config=clip_chart, data_source_config=preset.data_source_config,
            dataset_config=preset.dataset_config, fun_fact_config=preset.fun_fact_config,
            export_config=export, project_root=args.project_root, progress_callback=progress).run()
        report["clip"] = result.output_file
        report["clip_frames"] = result.frames_rendered
    after = {str(p): sha256(p.read_bytes()).hexdigest() for p in (args.project, csv)}
    assert before == after, "Source project or data changed during validation."
    report["source_files_unchanged"] = True
    destination = output / "activity_timing_validation.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
