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
- Themes.
- Value format presets.
- Logo resolution and rendering.
- External JSON project files.
- Top-N bar selection and optional "Other" aggregation.
- CLI presets and CLI overrides.
- PNG frame rendering with Matplotlib.
- MP4 export with FFmpeg.
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
- CLI overrides can adjust output path, frames directory, title, theme, value
  format, fps, duration, size, and related options.

External project files are the preferred way to define reusable videos.

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
.venv\Scripts\python.exe src\main.py --list-value-formats
.venv\Scripts\python.exe src\main.py --list-easings
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

Current working branch:

```text
master
```

The project has been using a pattern of:

1. Implement feature.
2. Run tests and compile.
3. Run a real render when visual/pipeline behavior changes.
4. Commit.
5. Push to `origin/master`.

## Near-Term Roadmap

Recommended next steps:

1. Improve large-dataset performance.
2. Add richer visual polish: shadows, gradients, typography presets, and
   better title/source layout.
3. Add more chart types while preserving the same pipeline ideas.

## Non-Goals For Now

- Do not migrate away from Matplotlib until the current engine behavior is
  stable.
- Do not add a GUI before the CLI and JSON project workflow are robust.
- Do not replace the custom engine with a high-level chart-race package.
- Do not mix business data models with visual state models.
