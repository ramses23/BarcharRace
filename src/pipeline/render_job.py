from dataclasses import dataclass
from time import perf_counter

from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from core.bar_selector import BarSelector
from core.layout_engine import LayoutEngine
from core.motion_engine import MotionEngine
from core.timeline import Timeline
from exporters.video_exporter import VideoExporter
from importers.data_source_loader import DataSourceLoader
from models.scene import Scene
from renderer.bar_renderer import BarRenderer
from utils.frame_cleaner import clean_frame_directory
from validators.dataset_validator import DatasetValidator


@dataclass(frozen=True)
class RenderProfile:
    load_data_seconds: float = 0.0
    validate_data_seconds: float = 0.0
    build_timeline_seconds: float = 0.0
    cleanup_seconds: float = 0.0
    precompute_sprites_seconds: float = 0.0
    render_frames_seconds: float = 0.0
    export_video_seconds: float = 0.0
    total_seconds: float = 0.0


@dataclass(frozen=True)
class RenderResult:
    frames_rendered: int
    transitions_rendered: int
    removed_frames: int
    output_file: str
    profile: RenderProfile

    @property
    def average_frame_seconds(self):
        if self.frames_rendered <= 0:
            return 0.0

        return self.profile.render_frames_seconds / self.frames_rendered


@dataclass(frozen=True)
class RenderProgress:
    stage: str
    message: str
    progress: float
    current: int = 0
    total: int = 0


class RenderJob:
    def __init__(
        self,
        config=None,
        data_source_config=None,
        dataset_config=None,
        progress_callback=None,
    ):
        self.config = config or ChartConfig()
        self.data_source_config = data_source_config or DataSourceConfig()
        self.dataset_config = dataset_config or DatasetConfig()
        self.progress_callback = progress_callback

    def run(self):
        total_started_at = perf_counter()
        timings = {}

        self._emit_progress("load_data", "Loading data", 0.02)
        dataframe = self._measure_stage(
            timings,
            "load_data",
            lambda: DataSourceLoader(self.data_source_config).load(),
        )
        self._emit_progress("validate_data", "Validating dataset", 0.08)
        dataframe = self._measure_stage(
            timings,
            "validate_data",
            lambda: DatasetValidator(config=self.dataset_config).validate(dataframe),
        )
        self._emit_progress("build_timeline", "Building timeline", 0.16)
        timeline = self._measure_stage(
            timings,
            "build_timeline",
            lambda: Timeline(dataframe, config=self.dataset_config),
        )
        years = timeline.get_years()

        if len(years) < 2:
            raise ValueError("RenderJob requires at least two time periods.")

        selector = BarSelector(config=self.config.selection)
        layout = LayoutEngine(config=self.config)
        motion = MotionEngine(animation_config=self.config.animation)
        renderer = BarRenderer(output_dir=self.config.frames_dir, config=self.config)
        exporter = VideoExporter(config=self.config)

        self._emit_progress("cleanup", "Cleaning previous frames", 0.22)
        removed_frames = self._measure_stage(
            timings,
            "cleanup",
            lambda: clean_frame_directory(
                self.config.frames_dir,
                pattern=self.config.frame_file_pattern,
            ),
        )
        print(f"Frames anteriores eliminados: {removed_frames}")

        self._emit_progress("precompute_sprites", "Preparing chart layout", 0.28)
        sprites_by_year = self._measure_stage(
            timings,
            "precompute_sprites",
            lambda: self._build_sprites_by_year(
                timeline=timeline,
                years=years,
                selector=selector,
                layout=layout,
            ),
        )

        frame_id = 0
        transitions_rendered = 0
        total_frame_count = max(
            1,
            (len(years) - 1) * self.config.steps_per_transition,
        )

        render_started_at = perf_counter()
        self._emit_progress(
            "render_frames",
            "Rendering frames",
            0.35,
            current=0,
            total=total_frame_count,
        )
        for i in range(len(years) - 1):
            year_a = years[i]
            year_b = years[i + 1]

            print(f"Transicion {year_a} -> {year_b}")

            start_sprites = sprites_by_year[year_a]
            end_sprites = sprites_by_year[year_b]

            frames = motion.interpolate_sprites(
                start_sprites,
                end_sprites,
                steps=self.config.steps_per_transition,
            )

            for step_index, frame_sprites in enumerate(frames):
                scene = self._build_scene(
                    year_a=year_a,
                    year_b=year_b,
                    step_index=step_index,
                    total_steps=len(frames),
                    bars=frame_sprites,
                )

                renderer.render(
                    scene,
                    filename=self.config.frame_filename(frame_id),
                )

                frame_id += 1
                self._emit_render_frame_progress(frame_id, total_frame_count)

            transitions_rendered += 1

        renderer.close()
        timings["render_frames"] = perf_counter() - render_started_at

        self._emit_progress("export_video", "Exporting MP4", 0.92)
        self._measure_stage(timings, "export_video", exporter.export)

        profile = self._build_profile(
            timings=timings,
            total_seconds=perf_counter() - total_started_at,
        )

        print("Video generado correctamente.")
        self._print_profile(profile)
        self._emit_progress("complete", "Video rendered", 1.0)

        return RenderResult(
            frames_rendered=frame_id,
            transitions_rendered=transitions_rendered,
            removed_frames=removed_frames,
            output_file=self.config.output_file,
            profile=profile,
        )

    def _measure_stage(self, timings, name, callback):
        started_at = perf_counter()
        result = callback()
        timings[name] = perf_counter() - started_at
        return result

    def _emit_progress(self, stage, message, progress, current=0, total=0):
        if self.progress_callback is None:
            return

        progress = max(0.0, min(1.0, float(progress)))
        self.progress_callback(
            RenderProgress(
                stage=stage,
                message=message,
                progress=progress,
                current=current,
                total=total,
            )
        )

    def _emit_render_frame_progress(self, frame_id, total_frame_count):
        frame_progress = frame_id / total_frame_count
        progress = 0.35 + (0.55 * frame_progress)
        self._emit_progress(
            "render_frames",
            "Rendering frames",
            progress,
            current=frame_id,
            total=total_frame_count,
        )

    def _build_profile(self, timings, total_seconds):
        return RenderProfile(
            load_data_seconds=timings.get("load_data", 0.0),
            validate_data_seconds=timings.get("validate_data", 0.0),
            build_timeline_seconds=timings.get("build_timeline", 0.0),
            cleanup_seconds=timings.get("cleanup", 0.0),
            precompute_sprites_seconds=timings.get("precompute_sprites", 0.0),
            render_frames_seconds=timings.get("render_frames", 0.0),
            export_video_seconds=timings.get("export_video", 0.0),
            total_seconds=total_seconds,
        )

    def _print_profile(self, profile):
        print(
            "Perfil de render: "
            f"load={profile.load_data_seconds:.3f}s, "
            f"validate={profile.validate_data_seconds:.3f}s, "
            f"timeline={profile.build_timeline_seconds:.3f}s, "
            f"cleanup={profile.cleanup_seconds:.3f}s, "
            f"precompute={profile.precompute_sprites_seconds:.3f}s, "
            f"render={profile.render_frames_seconds:.3f}s, "
            f"export={profile.export_video_seconds:.3f}s, "
            f"total={profile.total_seconds:.3f}s"
        )

    def _build_sprites_by_year(self, timeline, years, selector, layout):
        sprites_by_year = {}

        for year in years:
            bars = selector.select(timeline.get_frame(year))
            sprites_by_year[year] = layout.build(bars)

        return sprites_by_year

    def _build_scene(self, year_a, year_b, step_index, total_steps, bars):
        progress = step_index / (total_steps - 1) if total_steps > 1 else 1
        display_year = year_a + (year_b - year_a) * progress

        return Scene(
            title=self.config.title,
            subtitle=f"{year_a} -> {year_b}",
            time_label=f"{display_year:.0f}",
            source_label=self.data_source_config.source_label,
            bars=bars,
        )
