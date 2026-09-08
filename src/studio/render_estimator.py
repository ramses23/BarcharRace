"""Machine-local, explicitly requested production-raster microbenchmark."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from pipeline.render_job import RenderJob
from studio.project_draft import project_fingerprint


def sample_global_frames(start, end, count=16):
    if not 0 <= start < end or not 1 <= count <= 20:
        raise ValueError("Invalid sample window or count.")
    count = min(count, end - start)
    if count == 1:
        return (start,)
    return tuple(start + i * (end - start - 1) // (count - 1) for i in range(count))


def human_render_time(seconds):
    seconds = max(1, round(seconds))
    if seconds < 60:
        return f"{seconds} sec"
    if seconds < 1200:
        minutes, remainder = divmod(seconds, 60)
        return f"{minutes} min" + (f" {remainder} sec" if remainder else "")
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, remainder = divmod(minutes, 60)
    return f"{hours} h" + (f" {remainder} min" if remainder else "")


@dataclass(frozen=True)
class RenderEstimate:
    start_frame: int
    end_frame: int
    sample_frames: tuple[int, ...]
    warmup_frames: int
    median_frame_seconds: float
    estimated_seconds: float
    startup_seconds: float
    wall_seconds: float
    sample_seconds: tuple[float, ...]

    @property
    def output_frames(self):
        return self.end_frame - self.start_frame


def estimate_render_job(job, *, clock=perf_counter):
    """Measure production RGBA drawing, not FFmpeg, disk IO or CPU throttling."""
    started = clock()
    timings, warmups, window, sampled = [], [], [], []

    def select(start, end):
        window.extend((start, end))
        sampled.extend(sample_global_frames(start, end))
        return sampled

    def consume(scene, renderer):
        if not timings:
            for _ in range(2):
                before = clock()
                renderer.render_rgba(scene)
                warmups.append(clock() - before)
        before = clock()
        renderer.render_rgba(scene)
        timings.append(clock() - before)

    result = job.run(frame_sampler=select, frame_consumer=consume)
    cost = median(timings)
    # Preparation is measured once. Only excess first-frame initialization
    # over a warm frame is added; encoding/finalization has no invented factor.
    startup = max(0., result.profile.total_seconds - result.profile.render_frames_seconds)
    startup += max(0., warmups[0] - cost)
    return RenderEstimate(window[0], window[1], tuple(sampled), len(warmups), cost,
        startup + cost * (window[1] - window[0]), startup, clock() - started, tuple(timings))


def estimate_cache_key(preset, project_root):
    """Conservative full-project key, including input asset stat signatures.

    Uses the existing project fingerprint, not preview's FPS-excluding key.
    File bytes aren't read on each rerun. Output files are deliberately absent
    from asset signatures: merely finishing a render must not invalidate it.
    """
    payload = asdict(preset)
    root = Path(project_root).resolve()
    chart = preset.chart_config
    paths = [preset.data_source_config.csv_path, preset.data_source_config.sqlite_database_path,
        chart.logos_dir, chart.background_image_path, chart.bar_texture_custom_image,
        preset.fun_fact_config.source,
        *preset.dataset_config.category_logos.values(),
        *preset.dataset_config.category_secondary_logos.values()]
    if preset.fun_fact_config.enabled and preset.fun_fact_config.source:
        source = Path(preset.fun_fact_config.source)
        source = source if source.is_absolute() else root / source
        try:
            facts = json.loads(source.read_text(encoding="utf-8"))
            paths.extend(item.get("image") for item in facts.get("fun_facts", [])
                         if isinstance(item, dict) and item.get("image"))
        except (OSError, ValueError, AttributeError):
            pass  # The production loader reports invalid inputs on Estimate.
    signatures = []
    for value in paths:
        if not value:
            continue
        path = Path(value)
        path = path if path.is_absolute() else root / path
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_dir():
                continue
            try:
                stat = candidate.stat()
                signatures.append((str(candidate.resolve()), stat.st_size, stat.st_mtime_ns))
            except OSError:
                signatures.append((str(candidate), None, None))
    return project_fingerprint({"preset": payload, "assets": signatures, "estimator_version": 1}, root)


def cached_estimate(cache, key, job_factory, *, render_active=False):
    if render_active:
        raise RuntimeError("Wait for the active render before estimating.")
    if key in cache:
        return cache[key]
    result = estimate_render_job(job_factory())
    # Per-session, bounded transient storage; never persisted in project JSON.
    cache.clear()
    cache[key] = result
    return result


def job_from_preset(preset, project_root):
    return RenderJob(config=preset.chart_config, data_source_config=preset.data_source_config,
        dataset_config=preset.dataset_config, fun_fact_config=preset.fun_fact_config,
        export_config=preset.export_config, project_root=project_root, output_file_is_effective=True)
