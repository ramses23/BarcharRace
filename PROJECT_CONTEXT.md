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
- Per-project color or image backgrounds, with PNG/JPEG/WebP upload and cover,
  contain, or stretch fitting. Background images are prepared once per render.
- Reusable layout presets.
- Auto-fit visible bars to the vertical capacity of the active layout.
- Configurable typography weights and max widths for title, subtitle, time
  label, and source label.
- Reusable typography presets.
- Four configurable bar shapes: rectangle, rounded, capsule, and lollipop.
- Configurable bar borders, shadows, and gradients, exposed through a live
  appearance editor in Project Studio.
- Bar appearance has a backward-compatible `simple` mode and an `advanced`
  material mode. Advanced mode supports multi-direction two/three-color fills,
  procedural or custom textures, bevel, inner shadow/glow, top/bottom depth,
  outer glow, shine, row tracks, and independent logo/label/value placement.
  Logos can be outside-left, inside-left, inside-right, or hidden, with adaptive,
  circular, rounded, or square masks plus independent padding, background, and
  border. Lollipop inside-left logos add a circular start socket; inside-right
  logos occupy the endpoint circle. Legacy `outside`/`inside` values are still
  accepted. Category label alignment is independent from its position and can
  be automatic, left, centered, or right within the allocated label area.
- Projected shadow remains a separate layer from bevel, inner shadow, and glow.
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
- `BarRenderer` reuses a single Matplotlib figure/axis and a bounded set of bar,
  shadow, logo, and text artists. Frames update artist properties instead of
  clearing the axis and rebuilding every artist.
- Gradient bars are rendered as one reusable `PolyCollection` with a 64-segment
  baseline per visible bar plus localized curve detail, avoiding a separate
  bicubic `AxesImage` resample for every bar on every frame.
- Advanced materials use one persistent clipped `AxesImage` per visible slot.
  The 256x64 RGBA material is cached by category color, while track, projected
  shadow, glow, border, logo, and text artists remain reusable. Do not route
  simple projects through this path; the simple `PolyCollection` is faster.
  A repeated eight-bar 1080p check measured about 0.0852s/frame for Simple,
  0.1516s/frame for Advanced Fill, and 0.1672s/frame for the fully layered
  Advanced sample. Treat the extra cost as an explicit quality tradeoff.
- Render profiling separates frame drawing time from PNG save time to guide further renderer or exporter optimization.
- PNG frame save compression is configurable through
  `ChartConfig.png_compress_level` from 0 to 9; the default is 1 to prioritize
  render speed over temporary PNG size. On the real 456-frame national team
  dataset, level 1 produced runs around 149.7s to 159.4s total, with PNG save
  time still around 121.9s to 128.6s. Level 0 produced about 161.0s total with
  130.1s in PNG saving. Treat PNG compression changes as a non-solution for
  this workload.
- `ChartConfig.frame_output_mode="ffmpeg_stream"` bypasses temporary PNG files
  and sends raw RGBA frames to FFmpeg stdin. On the real 456-frame national-team
  dataset, streaming reduced the measured total from 151.918s to 114.556s.
  Reusing Matplotlib artists reduced the same streaming render to 92.622s,
  and batching gradient bars into a segmented collection reduced it further to
  54.172s (456 frames at 1920x1080 and 24 FPS).
- `RenderJob` supports an optional progress callback for UI progress updates.
- Synthetic larger-dataset profiling tool in `src/tools/profile_large_dataset.py`.
- CLI presets and CLI overrides.
- Local Streamlit project editor in `src/ui/project_studio.py`.
- Project Studio can create new project JSON files and open/edit existing
  `projects/*.json` files while preserving advanced fields that are not exposed
  in the form yet.
- Project Studio groups its form into four workflow tabs: `Data & content`,
  `Canvas & text`, `Bars & categories`, and `Animation & output`. Project and
  CSV loading live in the sidebar, while dataset previews and advanced panels
  remain collapsed until needed. The redundant `Theme` and `Typography`
  selectors are hidden, but their stored values remain compatible with older
  project files.
- For new projects, Project Studio derives the title, project name, project JSON
  path, output MP4 path, and frames directory from the selected CSV filename.
- Project Studio can render selected-year previews and transition-point
  previews before generating the full video.
- Project Studio exposes font-family selectors for title, subtitle, category
  labels, values, date, source, and ranking. The selectors use a curated list
  of up to 30 common installed fonts and render each option in its own family.
  Each element falls back to the active theme font when its family is null.
- Project Studio exposes point-size controls for title, subtitle, category,
  value, date, source, and ranking text. A visual layout editor lets users drag
  title, subtitle, date, and source on a scaled canvas, nudge with arrow keys,
  align horizontally, and reset to preset positions. X/Y coordinates remain
  the persisted format. Unset title/subtitle X coordinates inherit
  `ChartConfig.left_margin` for backward compatibility.
- Project Studio exposes independent text colors for title, subtitle, category,
  value, date, source, and ranking. The optional `*_text_color` fields inherit
  the legacy theme colors when absent, preserving older project rendering.
- `AnimationConfig.motion_mode` supports `transition_easing` (legacy default)
  and `continuous`. Continuous mode uses bounded Catmull-Rom interpolation with
  neighboring annual keyframes, keeps velocity continuous for persistent bars,
  preserves eased fades for entries/exits, and emits year-boundary frames once.
- Project Studio shows render progress while launching a final video render.
- Project Studio shows the estimated playback duration, transition count, and
  frame count live from the dataset periods, steps per transition, motion mode,
  and FPS. The estimate is playback length, not render completion time, and
  shares its frame-count formula with `RenderJob`.
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
        -> PNG frames -> VideoExporter -> MP4 (png_sequence, optional fallback)
        -> RGBA memory -> FFmpeg stdin -> MP4 (ffmpeg_stream, default)
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
- `VideoExporter` exports PNG sequences or opens a raw RGBA FFmpeg stream.
- `ChartConfig.frame_output_mode` selects `png_sequence` or `ffmpeg_stream`.

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
