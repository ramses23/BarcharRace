# BarChartStudio

BarChartStudio is a Python animation engine for creating professional
Bar Chart Race videos.

The goal is not to wrap an existing library such as `bar_chart_race`.
The project builds its own modular pipeline so the same engine can later
support other animated visualizations such as line chart races, bubble
charts, animated scatter plots, and timeline animations.

## Current Capabilities

- Load datasets from CSV or SQLite.
- Validate and normalize input data before rendering.
- Build a time-based `Timeline`.
- Convert business data into visual bar sprites.
- Interpolate bar movement and values between periods.
- Render full scenes with title, subtitle, source label, bars, values, and
  a large time label.
- Render rank labels for each bar.
- Resolve and render optional logos for bars.
- Export PNG frames to MP4 with FFmpeg.
- Run project presets from the command line.
- Override preset render options from the command line.
- Render external JSON project files.
- Run a minimal automated test suite with `unittest`.

## Requirements

- Python 3.13
- FFmpeg available in `PATH`
- Python packages from `requirements.txt`

The project already expects a local virtual environment at `.venv`.

## Setup

From the project root:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If the SQLite sample database needs to be recreated:

```powershell
.venv\Scripts\python.exe src\create_database.py
```

## Running The Project

List available presets:

```powershell
.venv\Scripts\python.exe src\main.py --list-presets
```

Run the default preset:

```powershell
.venv\Scripts\python.exe src\main.py
```

Run a specific preset:

```powershell
.venv\Scripts\python.exe src\main.py csv_sample
.venv\Scripts\python.exe src\main.py sqlite_population
.venv\Scripts\python.exe src\main.py youtube_1080p
```

Run an external project file:

```powershell
.venv\Scripts\python.exe src\main.py --project projects/sample_project.json
```

List available themes, value formats, and easing presets:

```powershell
.venv\Scripts\python.exe src\main.py --list-themes
.venv\Scripts\python.exe src\main.py --list-value-formats
.venv\Scripts\python.exe src\main.py --list-easings
```

Override preset options from the command line:

```powershell
.venv\Scripts\python.exe src\main.py csv_sample --output output/custom.mp4
.venv\Scripts\python.exe src\main.py csv_sample --theme midnight_contrast
.venv\Scripts\python.exe src\main.py csv_sample --title "Custom Race"
.venv\Scripts\python.exe src\main.py csv_sample --fps 60 --duration 2
```

Common overrides:

| Option | Effect |
|---|---|
| `--output` | MP4 output path |
| `--frames-dir` | temporary PNG frames directory |
| `--title` | chart title |
| `--theme` | named visual theme |
| `--value-format` | named value formatter |
| `--fps` | video frames per second |
| `--steps` | frames generated per transition |
| `--duration` | seconds per transition |
| `--width` | render width in pixels |
| `--height` | render height in pixels |

Overrides can also be applied on top of an external project file:

```powershell
.venv\Scripts\python.exe src\main.py --project projects/sample_project.json --theme midnight_contrast --output output/custom.mp4
```

## Project Files

External project files are JSON documents. They let you create new videos
without editing Python source files.

Example:

```json
{
  "name": "sample_project",
  "base_preset": "csv_sample",
  "chart": {
    "title": "External Project Demo",
    "output_file": "output/external_project.mp4",
    "frames_dir": "output/external_project_frames",
    "theme": "clean_report",
    "value_format": "decimal",
    "fps": 24,
    "steps_per_transition": 24,
    "rank_labels_enabled": true,
    "rank_label_prefix": "#",
    "label_min_x": 40,
    "value_label_gap": 16
  },
  "animation": {
    "easing": "ease_out_cubic",
    "enter_exit": true,
    "value_smoothing": true
  },
  "data_source": {
    "source_type": "csv",
    "csv_path": "data/datasets/sample_dynamic.csv"
  },
  "dataset": {
    "year_column": "year",
    "name_column": "country",
    "value_column": "value"
  }
}
```

Supported top-level keys:

| Key | Meaning |
|---|---|
| `name` | display name used by the CLI |
| `base_preset` | optional preset to extend |
| `chart` | `ChartConfig` values |
| `animation` | `AnimationConfig` values |
| `data_source` | `DataSourceConfig` values |
| `dataset` | `DatasetConfig` values |

Named `theme` and `value_format` values are resolved through the existing
theme and value-format registries.

## Presets

| Preset | Data source | Output |
|---|---|---|
| `csv_sample` | `data/datasets/sample_dynamic.csv` | `output/video.mp4` |
| `sqlite_population` | `data/database/barchart.db`, table `population` | `output/sqlite_population.mp4` |
| `youtube_1080p` | `data/datasets/sample_dynamic.csv` | `output/youtube_1080p.mp4` |

Presets are defined in:

```text
src/config/project_preset.py
```

Each preset combines:

- `ChartConfig`
- `ThemeConfig`
- `DataSourceConfig`
- `DatasetConfig`

## Animation

Motion behavior is configured with `AnimationConfig`.

Available easing presets:

| Easing | Notes |
|---|---|
| `linear` | constant interpolation |
| `smoothstep` | default smooth in/out |
| `ease_in_out` | compatibility alias for `smoothstep` |
| `ease_in_cubic` | slow start |
| `ease_out_cubic` | fast start, soft landing |
| `ease_in_out_cubic` | stronger cubic in/out |

Animation fields:

| Field | Meaning |
|---|---|
| `easing` | easing preset used for position, width, height, and optionally values |
| `enter_exit` | fades bars in and out when they appear or disappear |
| `value_smoothing` | uses easing for numeric values when true, linear values when false |

Bar opacity is part of `BarSprite`, so the renderer can fade bars, labels,
values, and logos consistently.

## Rank Labels

`LayoutEngine` assigns a visual rank to each `BarSprite` based on sorted
values. `MotionEngine` interpolates that rank while bars move, and
`BarRenderer` draws the current rank beside the bar.

Rank labels are configured in `ChartConfig`:

```text
rank_labels_enabled
rank_label_prefix
rank_label_font_size
rank_label_gap
```

The default label format is `#1`, `#2`, `#3`.

## Text Fitting

Bar labels and value labels include basic collision handling.

Long bar names are truncated with `...` so they stay inside the available
label column. Value labels are drawn outside the bar when they fit, moved
inside the bar when the right edge would overflow, or clamped to a safe
right edge when the bar is too small.

Text fitting is configured in `ChartConfig`:

```text
label_min_x
text_average_char_width
value_label_gap
value_label_edge_padding
value_label_inside_padding
value_label_inside_color
```

For reusable video definitions that should not require Python edits, prefer
external project files in:

```text
projects/
```

## Value Formats

Numeric value formatting is configured with `ValueFormatConfig`.

Available named formats:

| Format | Example |
|---|---|
| `decimal` | `1,234.5` |
| `integer` | `1,235` |
| `population_millions` | `282.2M` |
| `money_usd` | `$1,235` |
| `percentage` | `75.6%` |
| `compact` | `1.2K`, `2.5M`, `3.2B` |

Formats are defined in:

```text
src/config/value_format_config.py
```

Example usage in a preset:

```python
from config.value_format_config import get_value_format

ChartConfig(
    value_format=get_value_format("population_millions")
)
```

## Themes

Visual styling is configured with `ThemeConfig`.

Available named themes:

| Theme | Notes |
|---|---|
| `studio_light` | Default warm light theme |
| `clean_report` | White report-style theme |
| `midnight_contrast` | High-contrast dark theme |

Themes control:

- background color
- primary text color
- muted text color
- base font family
- bar color palette

Themes are defined in:

```text
src/config/theme_config.py
```

Example usage in a preset:

```python
from config.theme_config import get_theme

ChartConfig(
    theme=get_theme("clean_report")
)
```

## Running Tests

Run the full test suite:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Compile source and tests:

```powershell
.venv\Scripts\python.exe -m compileall src tests
```

Current test coverage includes:

- `value_formatter`
- `ValueFormatConfig`
- `AnimationConfig`
- `ThemeConfig`
- `ColorPalette`
- `LayoutEngine` rank assignment
- text fitting and value-label layout
- `DatasetValidator`
- `DataSourceLoader`
- `RenderJob`
- CLI preset overrides
- external project file loader
- real render integration test with FFmpeg

## Architecture

Current render pipeline:

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

High-level source layout:

```text
src/
  animation/
  cli/
  config/
  core/
  exporters/
  importers/
  models/
  pipeline/
  renderer/
  utils/
  validators/
  main.py

projects/
tests/
```

## Important Concepts

### BarData

Business data for a bar.

```text
name
value
optional color
```

### BarSprite

Visual state for a bar.

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

### Scene

A complete renderable frame.

```text
title
subtitle
time_label
source_label
bars
```

### RenderJob

The reusable project runner. It owns the render workflow and returns a
`RenderResult`.

```python
from main import run_preset

result = run_preset("sqlite_population")
print(result)
```

## Data Format

Default datasets use these columns:

```csv
year,country,value
2000,USA,100
2000,Mexico,80
2001,USA,90
```

Column names are configured in:

```text
src/config/dataset_config.py
```

The validator checks:

- required columns
- empty dataset
- null values
- blank names
- numeric years
- integer years
- numeric values
- negative values
- duplicated `year + country` combinations

## Outputs

Generated files are written under:

```text
output/
```

Frame files use:

```text
output/frames/frame_0000.png
```

Before each render, old `frame_*.png` files are removed from the configured
frames directory so FFmpeg cannot mix old and new frames.

`output/` is ignored by Git.

## Logos

Optional logos are resolved from:

```text
logos/
```

Supported raster formats:

```text
.png
.jpg
.jpeg
.webp
```

Logo filenames are matched against bar names using normalized names. For
example, these files can match these bars:

| Bar name | Logo filename |
|---|---|
| `USA` | `logos/USA.png` |
| `United States` | `logos/United States.png` |
| `Mexico` | `logos/mexico.jpg` |

If a logo is missing, the bar still renders normally.

Logo behavior is configured in:

```text
ChartConfig.logos_enabled
ChartConfig.logos_dir
ChartConfig.logo_size
ChartConfig.logo_file_extensions
```

Sample development logos can be generated with:

```powershell
.venv\Scripts\python.exe src\tools\create_sample_logos.py
```

This creates:

```text
logos/USA.png
logos/Mexico.png
logos/Canada.png
```

## Development Notes

- `PROJECT_CONTEXT.md` contains the continuity guide for future Codex sessions.
  Read it before making architecture or roadmap decisions.
- `main.py` should stay thin. It is only the CLI entry point.
- Render workflow logic belongs in `src/pipeline/render_job.py`.
- Visual configuration belongs in `ChartConfig`.
- Data source configuration belongs in `DataSourceConfig`.
- Dataset schema and validation rules belong in `DatasetConfig` and
  `DatasetValidator`.
- Renderer code should receive a `Scene`, not raw data.
- Future chart types should reuse the same source, validation, timeline,
  scene, renderer, and exporter patterns where possible.

## Next Engineering Steps

- Add configurable top-N filtering and trailing "other" handling for larger datasets.
