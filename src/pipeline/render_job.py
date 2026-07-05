from dataclasses import dataclass

from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
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
class RenderResult:
    frames_rendered: int
    transitions_rendered: int
    removed_frames: int
    output_file: str


class RenderJob:
    def __init__(self, config=None, data_source_config=None, dataset_config=None):
        self.config = config or ChartConfig()
        self.data_source_config = data_source_config or DataSourceConfig()
        self.dataset_config = dataset_config or DatasetConfig()

    def run(self):
        timeline = self._build_timeline()
        years = timeline.get_years()

        if len(years) < 2:
            raise ValueError("RenderJob requires at least two time periods.")

        layout = LayoutEngine(config=self.config)
        motion = MotionEngine()
        renderer = BarRenderer(output_dir=self.config.frames_dir, config=self.config)
        exporter = VideoExporter(config=self.config)

        removed_frames = clean_frame_directory(
            self.config.frames_dir,
            pattern=self.config.frame_file_pattern,
        )
        print(f"Frames anteriores eliminados: {removed_frames}")

        frame_id = 0
        transitions_rendered = 0

        for i in range(len(years) - 1):
            year_a = years[i]
            year_b = years[i + 1]

            print(f"Transicion {year_a} -> {year_b}")

            start_sprites = layout.build(timeline.get_frame(year_a))
            end_sprites = layout.build(timeline.get_frame(year_b))

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

            transitions_rendered += 1

        exporter.export()

        print("Video generado correctamente.")

        return RenderResult(
            frames_rendered=frame_id,
            transitions_rendered=transitions_rendered,
            removed_frames=removed_frames,
            output_file=self.config.output_file,
        )

    def _build_timeline(self):
        dataframe = DataSourceLoader(self.data_source_config).load()
        dataframe = DatasetValidator(config=self.dataset_config).validate(dataframe)
        return Timeline(dataframe, config=self.dataset_config)

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
