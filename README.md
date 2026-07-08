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
- Keep bar labels separated from rank-label columns in compact layouts.
- Keep very large value labels inside a safe data-area width.
- Draw the large time label as a background watermark behind chart content.
- Auto-fit visible bars to the available vertical layout space.
- Apply reusable layout presets for common video formats.
- Apply configurable font weights and max widths to title, subtitle, time
  label, and source label.
- Apply reusable typography presets.
- Render configurable soft shadows behind bars.
- Render configurable horizontal gradients on bars.
- Resolve and render optional logos for bars.
- Export PNG frames to MP4 with configurable FFmpeg quality options.
- Report render progress through a reusable `RenderJob` callback.
- Run project presets from the command line.
- Override preset render options from the command line.
- Render external JSON project files.
- Create, open, edit, and preview project files from a local Streamlit editor.
- Preview a selected year or transition point before rendering a full video.
- Render project-specific source labels instead of raw local file paths.
- Apply project-specific category labels and bar colors.
- Assign project-specific category logos from the local Streamlit editor.
- Limit large frames with configurable top-N selection and optional "Other".
- Precompute per-year sprites so transitions reuse prepared layout state.
- Report per-stage render profiling timings for larger-dataset tuning.
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
.venv\Scripts\python.exe src\main.py --project projects/global_electricity_sources.json
```

Run the local project editor:

```powershell
.venv\Scripts\python.exe -m streamlit run src\ui\project_studio.py
```

At the end of a render, the CLI prints a compact profiling line with the
seconds spent loading data, validating data, building the timeline,
precomputing sprites, rendering frames, exporting video, and running the full
job. Project Studio shows the same render profile after a video render,
including total frames, average seconds per frame, draw time, PNG save time, and render overhead.

Run a synthetic larger-dataset profiling render:

```powershell
.venv\Scripts\python.exe src\tools\profile_large_dataset.py --years 30 --categories 200 --top-n 20 --steps 4 --fps 6
```

The profiling tool generates a temporary CSV by default, renders a real video,
and prints the normal `RenderProfile` timings. Use `--csv-output` if you want
to keep the generated dataset for inspection.

List available themes, layout presets, typography presets, value formats, and
easing presets:

```powershell
.venv\Scripts\python.exe src\main.py --list-themes
.venv\Scripts\python.exe src\main.py --list-layouts
.venv\Scripts\python.exe src\main.py --list-typographies
.venv\Scripts\python.exe src\main.py --list-value-formats
.venv\Scripts\python.exe src\main.py --list-easings
```

Override preset options from the command line:

```powershell
.venv\Scripts\python.exe src\main.py csv_sample --output output/custom.mp4
.venv\Scripts\python.exe src\main.py csv_sample --theme midnight_contrast
.venv\Scripts\python.exe src\main.py csv_sample --layout vertical_shorts
.venv\Scripts\python.exe src\main.py csv_sample --typography editorial
.venv\Scripts\python.exe src\main.py csv_sample --title "Custom Race"
.venv\Scripts\python.exe src\main.py csv_sample --fps 60 --duration 2
.venv\Scripts\python.exe src\main.py csv_sample --video-crf 20 --ffmpeg-preset slow
```

Common overrides:

| Option | Effect |
|---|---|
| `--output` | MP4 output path |
| `--frames-dir` | temporary PNG frames directory |
| `--title` | chart title |
| `--theme` | named visual theme |
| `--layout` | named layout preset |
| `--typography` | named typography preset |
| `--value-format` | named value formatter |
| `--fps` | video frames per second |
| `--steps` | frames generated per transition |
| `--duration` | seconds per transition |
| `--width` | render width in pixels |
| `--height` | render height in pixels |
| `--video-codec` | FFmpeg video codec |
| `--video-pixel-format` | FFmpeg pixel format |
| `--video-crf` | FFmpeg CRF quality value |
| `--video-bitrate` | FFmpeg video bitrate, for example `8M` |
| `--ffmpeg-preset` | FFmpeg encoder preset, for example `slow` |

Overrides can also be applied on top of an external project file:

```powershell
.venv\Scripts\python.exe src\main.py --project projects/sample_project.json --layout square_social --typography compact --output output/custom.mp4
```

## Project Files

External project files are JSON documents. They let you create new videos
without editing Python source files.

`Project Studio` is a local Streamlit interface for creating and editing these
JSON files from a CSV. It can open existing files from `projects/*.json`,
inspect columns, derive new-project names and output paths from the selected
CSV filename, save a project file, render a selected year or transition preview
frame, and launch the final video render with visible progress. When it
edits an existing file, it preserves advanced JSON fields that are not exposed
in the form yet.

Example:

```json
{
  "name": "sample_project",
  "base_preset": "csv_sample",
  "chart": {
    "title": "External Project Demo",
    "output_file": "output/external_project.mp4",
    "frames_dir": "output/external_project_frames",
    "layout_preset": "youtube_1080p",
    "theme": "clean_report",
    "value_format": "decimal",
    "typography_preset": "editorial",
    "fps": 24,
    "steps_per_transition": 24,
    "png_compress_level": 1,
    "video_codec": "libx264",
    "video_pixel_format": "yuv420p",
    "video_crf": 18,
    "video_bitrate": null,
    "ffmpeg_preset": null,
    "rank_labels_enabled": true,
    "rank_label_prefix": "#",
    "rank_label_min_x": 96,
    "rank_label_label_gap": 18,
    "label_min_x": 40,
    "value_label_gap": 16,
    "value_label_min_x": null,
    "auto_fit_bar_count": true,
    "max_visible_bars": null,
    "bar_shadow_enabled": true,
    "bar_shadow_alpha": 0.12,
    "bar_shadow_offset_x": 5,
    "bar_shadow_offset_y": 4,
    "bar_gradient_enabled": true,
    "bar_gradient_lighten": 0.22
  },
  "animation": {
    "easing": "ease_out_cubic",
    "enter_exit": true,
    "value_smoothing": true
  },
  "selection": {
    "top_n": 3,
    "aggregate_other": false,
    "other_label": "Other",
    "other_color": "#A0A0A0"
  },
  "categories": {
    "USA": {
      "label": "United States",
      "color": "#4E79A7"
    },
    "Mexico": {
      "color": "#59A14F"
    }
  },
  "data_source": {
    "source_type": "csv",
    "csv_path": "data/datasets/sample_dynamic.csv",
    "source_label_override": "Source: BarChartStudio sample dataset"
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
| `selection` | `BarSelectionConfig` values |
| `categories` | optional labels and colors keyed by raw dataset category |
| `data_source` | `DataSourceConfig` values |
| `dataset` | `DatasetConfig` values |

Named `theme`, `layout_preset`, `typography_preset`, and `value_format` values
are resolved through their registries.

Category styles are keyed by the raw value from the dataset name column. Each
entry can define a display `label`, a bar `color`, a `logo`, or any combination
of those fields:

```json
"categories": {
  "Gas": {
    "label": "Natural gas",
    "color": "#F28E2B",
    "logo": "logos/gas.png"
  },
  "Solar": {
    "color": "#EDC948",
    "logo": "logos/solar.png"
  }
}
```

If a category has no custom color, the renderer keeps using the active theme
palette.

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

## Example Projects

Reusable project files live in:

```text
projects/
```

Included examples:

| Project file | Notes |
|---|---|
| `projects/sample_project.json` | Small default CSV demo |
| `projects/global_electricity_sources.json` | User-provided global electricity generation dataset |

The electricity example uses:

```text
data/datasets/global_electricity_sources.csv
```

That CSV currently uses the standard engine columns `year`, `country`, and
`value`, with values in TWh. If you replace it with another official dataset,
keep those columns or adjust the `dataset` section in the project file.

`data_source.source_label_override` lets a project show a clean source label
instead of a local file path.

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
rank_label_min_x
rank_label_label_gap
```

The default label format is `#1`, `#2`, `#3`.
`rank_label_min_x` keeps the rank column away from the canvas edge, and
`rank_label_label_gap` reserves space between the rank and the bar name.

## Visual Polish

Layout presets control canvas geometry and common positional fields:

```text
layout_preset
width
height
left_margin
right_margin
top_margin
bottom_margin
bar_height
bar_gap
title_y
subtitle_y
time_label_x
time_label_y
source_x
source_y
rank_label_gap
rank_label_min_x
rank_label_label_gap
```

Available layout presets:

| Preset | Notes |
|---|---|
| `youtube_1080p` | Default 16:9 1920x1080 video layout |
| `youtube_4k` | 16:9 3840x2160 layout with doubled geometry |
| `square_social` | 1080x1080 social layout |
| `vertical_shorts` | 1080x1920 vertical layout |
| `compact_dashboard` | 1280x720 denser dashboard-style layout |

`LayoutEngine` can automatically limit visible bars to the vertical space
available in the current layout:

```text
auto_fit_bar_count
max_visible_bars
```

`auto_fit_bar_count` is enabled by default. `max_visible_bars` can apply an
additional manual cap, or stay `null` to use only the layout capacity.

Bars can render a subtle configurable shadow behind the main rectangle. This is
controlled in `ChartConfig` or in external project files:

```text
bar_shadow_enabled
bar_shadow_color
bar_shadow_alpha
bar_shadow_offset_x
bar_shadow_offset_y
```

Shadows follow bar opacity, so entering and exiting bars fade consistently.

Bars can also render a horizontal gradient based on each bar's own color:

```text
bar_gradient_enabled
bar_gradient_lighten
```

When disabled, bars fall back to the original solid rectangle rendering.

Title, subtitle, time label, and source label typography can be tuned from
`ChartConfig` or a project file:

```text
typography_preset
title_font_weight
subtitle_font_weight
time_label_font_weight
source_font_weight
title_max_width
subtitle_max_width
source_max_width
```

The title, subtitle, and source label are truncated with `...` when they exceed
their configured widths or the remaining canvas width.

Available typography presets:

| Preset | Notes |
|---|---|
| `studio` | Default balanced text scale |
| `editorial` | Larger title/subtitle scale for polished 1080p videos |
| `compact` | Smaller text scale for denser charts |

## Text Fitting

Bar labels and value labels include basic collision handling.

Long bar names are truncated with `...` so they stay inside the available
label column. Value labels are drawn outside the bar when they fit, moved
inside the bar when the right edge would overflow, or clamped to a safe
right edge when the bar is too small. Very large value labels are truncated
inside the safe value-label area instead of stretching into the left label
column.

The large time label is rendered as a low-opacity background watermark behind
bars and source text, which keeps dense layouts readable.

Text width estimates use the configured render `dpi`, so Matplotlib point-size
fonts are fitted against pixel-based layout coordinates.

Text fitting is configured in `ChartConfig`:

```text
title_max_width
subtitle_max_width
source_max_width
label_min_x
rank_label_min_x
rank_label_label_gap
text_average_char_width
value_label_gap
value_label_edge_padding
value_label_min_x
value_label_inside_padding
value_label_inside_color
```

When `value_label_min_x` is `null`, the renderer uses the data area's left
margin when it fits inside the canvas, otherwise it falls back to `label_min_x`.

## Bar Selection

Large datasets can be limited before layout with `BarSelectionConfig`.

Selection fields:

| Field | Meaning |
|---|---|
| `top_n` | number of leading bars to keep, or `null` for all bars |
| `aggregate_other` | when true, hidden bars are summed into a trailing bar |
| `other_label` | display name for the aggregated trailing bar |
| `other_color` | optional color for the aggregated trailing bar |

When `top_n` is `10` and `aggregate_other` is true, the renderer shows the top
10 real bars plus one aggregated `Other` bar.

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
- layout presets
- typography presets
- `ColorPalette`
- `BarSelector`
- `LayoutEngine` rank assignment
- layout auto-fit bar capacity
- bar shadow rendering
- bar gradient rendering
- text fitting for title, subtitle, source, rank-aware bar labels, and
  value-label layout
- full-canvas Matplotlib renderer setup
- background time-label layering
- `DatasetValidator`
- `DataSourceLoader`
- `DataSourceConfig`
- `RenderJob`
- per-year sprite precomputation
- render progress callbacks
- render profiling metrics
- synthetic larger-dataset profiling tool
- configurable FFmpeg export command
- CLI preset overrides
- external project file loader
- Streamlit project editor helpers
- existing-project loading in Project Studio
- selected-year and transition preview rendering in Project Studio
- category labels and colors from project files
- explicit category logo paths from project files
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

## Frame Output

Temporary PNG frame writing is controlled with `png_compress_level` from `0` to
`9`. Lower values write frames faster and create larger temporary PNG files. The
default is `1`, optimized for render speed; final MP4 quality is still controlled
by FFmpeg settings.

## Video Export

FFmpeg export is configured through `ChartConfig`, project files, or CLI
overrides:

```text
video_codec
video_pixel_format
video_crf
video_bitrate
ffmpeg_preset
```

The default export uses:

```text
video_codec = libx264
video_pixel_format = yuv420p
video_crf = 18
```

CRF mode is the default quality mode. When `video_bitrate` is set, bitrate mode
is used and `video_crf` is omitted from the FFmpeg command.

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

Project files can also assign explicit logos per category:

```json
"categories": {
  "Coal": {
    "logo": "logos/coal.png"
  }
}
```

Project Studio can upload a complete logo folder, choose an existing file from
a logo folder, auto-match files whose names match category names, or upload a
logo for a category. Uploaded logo folders are copied under `logos/`, and
category logo paths are referenced from the project JSON.
Logo auto-matching runs against every category in the dataset, even when the
category editor only displays the first 80 rows. Applied logo matches are kept
in the editor session so subsequent preview and video renders use the full
matched set.

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

- Continue Project Studio polish with publication-ready dataset-specific
  project presets and easier visual tuning controls.
