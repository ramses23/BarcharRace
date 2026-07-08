# Project Context For Future Codex Sessions

This file is the continuity guide for BarChartStudio. Read it before making
architecture or feature decisions. The README explains how to run the project;
this document explains why the project is shaped this way and how to keep it
moving in the same direction.

## Product Goal

BarChartStudio is a Python animation engine for producing professional
Bar Chart Race videos.

The long-term goal is not only to generate bar chart races. The goal is to
build a reusable visualization engine that can later support:

- Bar Chart Race
- Line Chart Race
- Bubble Chart
- Animated Scatter Plot
- Timeline Animations

Do not replace the engine with an existing high-level library such as
`bar_chart_race`. The project intentionally builds its own pipeline to keep
control over animation, rendering, layout, themes, logos, typography, and video
export.

## Current Status

The project is a usable MVP:

- CSV and SQLite data sources.
- Dataset validation.
- Timeline construction.
- BarData to BarSprite layout.
- Motion interpolation with configurable easing.
- Enter/exit opacity for bars.
- Rank labels.
- Text fitting for long labels and value labels.
- Rank-aware bar label fitting so names do not invade the rank-label column.
- Value labels are constrained to a safe data-area width for very large values.
- Title, subtitle, and source labels fit to both configured max widths and
  remaining canvas width.
- Themes.
- Reusable layout presets.
- Auto-fit visible bars to the vertical capacity of the active layout.
- Configurable typography weights and max widths for title, subtitle, time
  label, and source label.
- Reusable typography presets.
- Configurable bar shadows.
- Configurable bar gradients.
- Value format presets.
- Logo resolution and rendering.
- External JSON project files.
- Project-specific source labels through `DataSourceConfig.source_label_override`.
- Project-specific category labels and colors through the top-level
  `categories` section in external project files.
- Project-specific category logos through `categories.<raw_name>.logo`, with
  Project Studio support for uploading a logo folder, choosing individual
  logos, uploading individual logos, or auto-matching files by category name.
- A user-provided electricity project exists at
  `projects/global_electricity_sources.json` with data in
  `data/datasets/global_electricity_sources.csv`.
- Top-N bar selection and optional "Other" aggregation.
- Per-year sprite precomputation to avoid repeated selection and layout work
  across transitions.
- Basic per-stage render profiling for larger-dataset tuning, shown in CLI output and Project Studio after video renders.
- Renderer caches logos already resized to `ChartConfig.logo_size` to avoid repeatedly resampling large image assets per frame.
- `RenderJob` supports an optional progress callback for UI progress updates.
- Synthetic larger-dataset profiling tool in `src/tools/profile_large_dataset.py`.
- CLI presets and CLI overrides.
- Local Streamlit project editor in `src/ui/project_studio.py`.
- Project Studio can create new project JSON files and open/edit existing
  `projects/*.json` files while preserving advanced fields that are not exposed
  in the form yet.
- For new projects, Project Studio derives the title, project name, project JSON
  path, output MP4 path, and frames directory from the selected CSV filename.
- Project Studio can render selected-year previews and transition-point
  previews before generating the full video.
- Project Studio shows render progress while launching a final video render.
- PNG frame rendering with Matplotlib.
- Matplotlib axes are forced to fill the full figure so layout coordinates map
  directly to the output frame.
- Text fitting converts Matplotlib point-size fonts to pixel estimates with
  the configured DPI before truncating labels.
- The large time label is rendered as a background watermark behind bars and
  source text.
- MP4 export with configurable FFmpeg codec, CRF, bitrate, preset, and pixel
  format.
- Unit tests and a real FFmpeg integration test.

The latest technical direction is to make the engine robust for larger real
datasets, then continue improving visual polish.

## Architecture Contract

Keep the pipeline clean:

```text
JSON project file or ProjectPreset
    -> ChartConfig
    -> AnimationConfig
    -> ThemeConfig
    -> DataSourceConfig
    -> DatasetConfig
    -> RenderJob
        -> DataSourceLoader
        -> DatasetValidator
        -> Timeline
        -> BarData
        -> BarSelector
        -> LayoutEngine
        -> AssetResolver
        -> BarSprite
        -> per-year sprite cache
        -> MotionEngine
        -> Scene
        -> BarRenderer
        -> PNG frames
        -> VideoExporter
        -> MP4
```

Important boundaries:

- `main.py` must stay thin. It is only the CLI entry point.
- `RenderJob` owns orchestration of the render workflow.
- `RenderJob` may report progress, but UI-specific rendering of that progress
  belongs outside the pipeline.
- Importers load data only. They should not know about rendering.
- Validators validate data only. They should not know about rendering.
- `Timeline` exposes frame data by period.
- `LayoutEngine` converts business data into visual bar sprites.
- `BarSelector` limits or aggregates business data before layout.
- `MotionEngine` interpolates visual state between sprites.
- `Scene` is the renderer input.
- `BarRenderer` receives a `Scene`; it should not fetch data or build timeline
  state.
- `VideoExporter` only exports frames to video.

## Model Meanings

`BarData` is business data:

```text
name
value
optional color
```

`BarSprite` is visual state:

```text
name
value
color
rank
x
y
width
height
optional logo_path
opacity
```

`Scene` is a complete renderable frame:

```text
title
subtitle
time_label
source_label
bars
```

Avoid reintroducing overlapping models such as `BarState`. Visual animation
should work on `BarSprite`.

## Configuration Direction

Prefer configuration over code edits for user-facing video definitions.

Current configuration layers:

- Internal presets live in `src/config/project_preset.py`.
- External reusable project files live in `projects/*.json`.
- CLI overrides can adjust output path, frames directory, title, theme, layout
  preset, value format, typography preset, fps, duration, size, and related
  FFmpeg export options.
- Project files can define category-specific display labels and colors in a
  top-level `categories` section keyed by the raw dataset category name.
- Category logo paths also belong in that `categories` section. Keep them keyed
  by the raw dataset category name so aliases do not break logo assignment.
- Project Studio can auto-match logo files by comparing normalized category
  names to normalized logo filenames, including case, spaces, underscores, and
  simple accent differences.
- Uploaded logo folders are copied under `logos/`, and the copied folder becomes
  the active logo folder for category matching.
- Category editing displays the first 80 categories for usability, but logo
  auto-matching uses every category in the dataset.
- Applied logo matches are persisted in Streamlit session state so preview and
  video renders include matched logos beyond the visible category rows.

External project files are the preferred way to define reusable videos.
The Streamlit editor should remain a convenience layer that creates, opens, and
edits project JSON files, renders preview frames, and launches `RenderJob`. It
should not duplicate timeline, layout, motion, renderer, or exporter logic.
When editing an existing project, preserve JSON fields that are not currently
represented by form controls.

## Development Rules

When adding a feature:

- Keep changes modular and close to the responsible layer.
- Add or update tests when behavior changes.
- Update README when user-facing behavior changes.
- Update this file when direction, architecture, or major workflow changes.
- Keep generated files out of Git. `output/` is ignored.
- Keep generated SQLite databases out of Git. `data/database/*.db` is ignored.
- Prefer small commits with clear messages.
- Push meaningful checkpoints to GitHub after verification.

When changing renderer behavior:

- Verify with at least one real render.
- Inspect a generated frame when visual layout changes.
- Keep text from overlapping where possible.
- Prefer configuration fields in `ChartConfig` for visual layout decisions.

When changing project JSON support:

- Update `ProjectFileLoader`.
- Add tests for accepted and rejected JSON fields.
- Update `projects/sample_project.json`.
- Update README.

## Verification Commands

Use these from the project root:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe -m compileall -q src tests
.venv\Scripts\python.exe src\main.py --project projects\sample_project.json
```

For quicker smoke renders, override output and timing:

```powershell
.venv\Scripts\python.exe src\main.py --project projects\sample_project.json --output output\smoke.mp4 --frames-dir output\smoke_frames --fps 6 --duration 1
```

Useful CLI discovery commands:

```powershell
.venv\Scripts\python.exe src\main.py --list-presets
.venv\Scripts\python.exe src\main.py --list-themes
.venv\Scripts\python.exe src\main.py --list-layouts
.venv\Scripts\python.exe src\main.py --list-typographies
.venv\Scripts\python.exe src\main.py --list-value-formats
.venv\Scripts\python.exe src\main.py --list-easings
```

Project Studio command:

```powershell
.venv\Scripts\python.exe -m streamlit run src\ui\project_studio.py
```

Larger-dataset profiling command:

```powershell
.venv\Scripts\python.exe src\tools\profile_large_dataset.py --years 30 --categories 200 --top-n 20 --steps 4 --fps 6
```

## Collaboration Style Requested By The User

The user wants professional, concrete change proposals. Before editing a
feature, provide a short summary table:

```text
File                         Action
src/core/layout_engine.py    Modify
src/core/motion_engine.py    Modify
tests/test_motion_engine.py  Add coverage
```

For each meaningful file, explain:

- file name
- reason for the change
- whether the whole file or only specific methods changed
- what behavior is affected

Avoid generic answers. Prefer implementing the next step, verifying it, and
summarizing the result.

## GitHub

Remote:

```text
https://github.com/ramses23/BarcharRace.git
```

Primary branch:

```text
master
```

Current interface-editor work branch:

```text
project-studio-editor
```

The project has been using a pattern of:

1. Implement feature.
2. Run tests and compile.
3. Run a real render when visual/pipeline behavior changes.
4. Commit.
5. Push to the active GitHub branch.

## Near-Term Roadmap

Recommended next steps:

1. Polish Project Studio with easier visual tuning controls.
2. Polish the electricity project with actual logo assets, refined copy, or
   source-specific visual adjustments if the user wants a more publication-ready
   output.
3. Add more chart types while preserving the same pipeline ideas.

## Non-Goals For Now

- Do not migrate away from Matplotlib until the current engine behavior is
  stable.
- Do not let the GUI duplicate engine pipeline logic; it should drive JSON
  project files and `RenderJob`.
- Do not replace the custom engine with a high-level chart-race package.
- Do not mix business data models with visual state models.
- Do not prioritize additional visual polish for aggregated `Other` bars unless
  the user asks for it explicitly.
