from dataclasses import replace

from config.project_file_loader import load_project_file
from core.bar_selector import BarSelector
from core.layout_engine import LayoutEngine
from core.motion_engine import MotionEngine
from core.timeline import Timeline
from importers.data_source_loader import DataSourceLoader
from models.scene import Scene
from renderer.bar_renderer import BarRenderer
from studio.package_paths import DEFAULT_PROJECT_ROOT, resolve_project_path
from validators.dataset_validator import DatasetValidator


def render_project_preview(
    project_path,
    output_dir="output/studio_preview",
    year=None,
    preview_mode="year",
    transition_progress=0.0,
    *,
    root_dir=None,
):
    root_path = _project_root(root_dir)
    project_path = resolve_project_path(
        project_path,
        project_root=root_path,
        required=True,
        field_name="project file",
    )
    preset = load_project_file(project_path)
    source_label = preset.data_source_config.source_label
    data_source_config = _resolved_data_source_config(
        preset.data_source_config,
        root_path,
    )
    dataset_config = _resolved_dataset_config(preset.dataset_config, root_path)
    chart_config = _resolved_chart_config(preset.chart_config, root_path)

    dataframe = DataSourceLoader(data_source_config).load()
    dataframe = DatasetValidator(config=dataset_config).validate(dataframe)
    timeline = Timeline(dataframe, config=dataset_config)
    years = timeline.get_years()

    if not years:
        raise ValueError("Preview requires at least one time period.")

    selector = BarSelector(config=chart_config.selection)
    layout = LayoutEngine(config=chart_config)
    preview_mode = _preview_mode(preview_mode, years)

    if preview_mode == "transition":
        year_a, year_b = _selected_transition_years(year, years)
        sprites = _transition_sprites(
            timeline=timeline,
            selector=selector,
            layout=layout,
            animation_config=chart_config.animation,
            year_a=year_a,
            year_b=year_b,
            progress=transition_progress,
        )
        progress = _clamped_progress(transition_progress)
        display_year = year_a + (year_b - year_a) * progress
        subtitle = f"{year_a} -> {year_b}"
        time_label = f"{display_year:.0f}"
    else:
        selected_year = _selected_year(year, years)
        sprites = _sprites_for_year(timeline, selector, layout, selected_year)
        subtitle = str(selected_year)
        time_label = str(selected_year)

    scene = Scene(
        title=chart_config.title,
        subtitle=subtitle,
        time_label=time_label,
        source_label=source_label,
        bars=sprites,
    )

    output_path = resolve_project_path(
        output_dir,
        project_root=root_path,
        required=True,
        field_name="preview output directory",
    )
    renderer = BarRenderer(output_dir=str(output_path), config=chart_config)

    try:
        return renderer.render(scene, filename="preview.png")
    finally:
        renderer.close()


def _project_root(root_dir):
    return resolve_project_path(
        root_dir if root_dir is not None else DEFAULT_PROJECT_ROOT,
        project_root=DEFAULT_PROJECT_ROOT,
        required=True,
        field_name="project root",
    )


def _resolved_data_source_config(config, project_root):
    if config.source_type == "csv":
        return replace(
            config,
            csv_path=str(
                resolve_project_path(
                    config.csv_path,
                    project_root=project_root,
                    required=True,
                    field_name="data_source.csv_path",
                )
            ),
        )

    if config.source_type == "sqlite":
        return replace(
            config,
            sqlite_database_path=str(
                resolve_project_path(
                    config.sqlite_database_path,
                    project_root=project_root,
                    required=True,
                    field_name="data_source.sqlite_database_path",
                )
            ),
        )

    return config


def _resolved_dataset_config(config, project_root):
    return replace(
        config,
        category_logos=_resolved_path_map(
            config.category_logos,
            project_root=project_root,
            field_name="dataset.category_logos",
        ),
        category_secondary_logos=_resolved_path_map(
            config.category_secondary_logos,
            project_root=project_root,
            field_name="dataset.category_secondary_logos",
        ),
    )


def _resolved_path_map(values, *, project_root, field_name):
    return {
        category: str(
            resolve_project_path(
                value,
                project_root=project_root,
                required=True,
                field_name=f"{field_name}[{category!r}]",
            )
        )
        for category, value in values.items()
    }


def _resolved_chart_config(config, project_root):
    background_path = resolve_project_path(
        config.background_image_path,
        project_root=project_root,
        required=config.background_mode == "image",
        field_name="chart.background_image_path",
    )
    texture_path = resolve_project_path(
        config.bar_texture_custom_image,
        project_root=project_root,
        required=(
            config.bar_texture_enabled
            and config.bar_texture_preset == "custom_image"
        ),
        field_name="chart.bar_texture_custom_image",
    )
    logos_dir = resolve_project_path(
        config.logos_dir,
        project_root=project_root,
        required=True,
        field_name="chart.logos_dir",
    )
    return replace(
        config,
        background_image_path=(
            str(background_path) if background_path is not None else None
        ),
        bar_texture_custom_image=(
            str(texture_path) if texture_path is not None else None
        ),
        logos_dir=str(logos_dir),
    )


def _selected_year(year, years):
    if year is None:
        return years[0]

    year = int(year)

    if year in years:
        return year

    return min(years, key=lambda candidate: abs(candidate - year))


def _selected_transition_years(year, years):
    if len(years) < 2:
        selected_year = _selected_year(year, years)
        return selected_year, selected_year

    start_years = years[:-1]
    selected_year = _selected_year(year, start_years)
    start_index = years.index(selected_year)

    return years[start_index], years[start_index + 1]


def _preview_mode(preview_mode, years):
    if preview_mode == "transition" and len(years) > 1:
        return "transition"

    return "year"


def _transition_sprites(
    timeline,
    selector,
    layout,
    animation_config,
    year_a,
    year_b,
    progress,
):
    start_sprites = _sprites_for_year(timeline, selector, layout, year_a)
    end_sprites = _sprites_for_year(timeline, selector, layout, year_b)
    motion = MotionEngine(animation_config=animation_config)

    if animation_config.continuous_motion:
        years = timeline.get_years()
        start_index = years.index(year_a)
        previous_year = years[start_index - 1] if start_index > 0 else year_a
        next_year = (
            years[start_index + 2]
            if start_index + 2 < len(years)
            else year_b
        )
        frames = motion.interpolate_sprites_continuous(
            _sprites_for_year(timeline, selector, layout, previous_year),
            start_sprites,
            end_sprites,
            _sprites_for_year(timeline, selector, layout, next_year),
            steps=100,
            include_start=True,
        )
    else:
        frames = motion.interpolate_sprites(
            start_sprites,
            end_sprites,
            steps=101,
        )
    frame_index = round(_clamped_progress(progress) * (len(frames) - 1))

    return frames[frame_index]


def _sprites_for_year(timeline, selector, layout, year):
    bars = selector.select(timeline.get_frame(year))
    return layout.build(bars)


def _clamped_progress(progress):
    try:
        progress = float(progress)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(1.0, progress))
