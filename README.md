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
- Render rectangle, rounded, capsule, and lollipop bar shapes.
- Render independent projected shadows, borders, gradients, textures, depth,
  glow, shine, and background tracks through Simple or Advanced appearance.
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
- Export/import complete project bundles with data and visual assets.
- Play and download the finished MP4 directly from Project Studio.
- Limit large frames with configurable top-N selection and optional "Other".
- Precompute per-year sprites so transitions reuse prepared layout state.
- Report per-stage render profiling timings for larger-dataset tuning.
- Run a complete local production from a strict version-2 brief, including
  dataset construction, optional local logos, project assembly, preflight, and
  an isolated MP4 render.
- Run a minimal automated test suite with `unittest`.

## Requirements

- Python 3.13
- FFmpeg available in `PATH`
- Exact Python packages from the locked `requirements.txt`

The project already expects a local virtual environment at `.venv`.

## Setup

The recommended first run creates `.venv` when necessary, installs the locked
packages, validates the environment, and then opens Project Studio:

```powershell
.\scripts\run_studio.ps1 -Setup
```

For an existing environment, install the lock directly with its interpreter:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Do not rely only on the `(.venv)` prompt text. If PowerShell resolves `python`
to a global installation, packages such as Streamlit may appear missing. The
launcher always calls the repository interpreter explicitly.

Validate the environment without starting the web server:

```powershell
.\scripts\run_studio.ps1 -CheckOnly
```

The underlying diagnostic command is also available directly:

```powershell
.venv\Scripts\python.exe src\tools\doctor.py
```

It checks Python and `.venv`, locked core package versions, repository write
access, the sample project, FFmpeg, and FFprobe.

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
.\scripts\run_studio.ps1
```

The explicit equivalent remains:

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

## Automated Production MVP

One local command can turn a version-2 production brief into a validated
dataset, a normal BarChartStudio project, and optionally a finished MP4:

```powershell
.venv\Scripts\python.exe src\tools\run_production.py `
  --brief production\briefs\examples\national_team_goals_demo.json `
  --root .
```

The command composes the existing components instead of implementing another
rendering path:

```text
ProductionBrief v2
    -> ProductionOrchestrator
        -> registered DatasetBuilder + DatasetValidator
        -> optional LocalLogoResolver
        -> ProductionProjectAssembler
        -> ProductionPreflightRunner
        -> optional ProductionRenderExecutor
            -> background render controller
            -> isolated render worker
            -> existing RenderJob
            -> MP4
```

A brief v2 has four required sections:

- `dataset`: registered builder, local source CSV, optional source SHA-256, and
  builder parameters.
- `assets`: optional primary and secondary local logo directories plus the
  missing-logo policy (`allow`, `warn`, or `error`).
- `project`: a local BarChartStudio template, project name, title, and source
  label.
- `render`: `enabled: true` to render an MP4, or `false` to stop after a ready
  preflight.

All referenced paths must remain below the explicit `--root`. Each job reserves
`output/.production_jobs/<job_id>/` exclusively and never overwrites an older
workspace. The principal results are:

```text
dataset/dataset.csv
project/project.json
render/video.mp4
manifests/*.json
status.json
```

Normal state order is `created`, `dataset_running`, `dataset_ready`,
`assets_ready`, `project_ready`, `preflight_ready`, `rendering`, and
`completed`. A render-disabled brief ends at `preflight_ready`; other terminal
states are `blocked`, `canceled`, and `failed`.

Project Studio currently lists only `projects/*.json`. To inspect or edit a
generated project there, copy the workspace's `project/project.json` to a new,
unique file under `projects/`, keep the production workspace in place, launch
Project Studio, and select the copied file from `Open project`. Its dataset and
asset references remain root-relative. Before rendering an edited copy, choose
a new output path so the completed production video is not reused.

This MVP is intentionally local and single-job. It has no automatic downloads,
remote logo discovery, scheduler or queue, retry/resume recovery, cloud
publication, or new automation UI. See `production/README.md` for the complete
example and brief format.

## Project Files

External project files are JSON documents. They let you create new videos
without editing Python source files.

The current project schema is version `1` and new files include
`"schema_version": 1`. Existing unversioned files are schema `0`: they are
migrated in memory when opened and written back as version 1 on the next save.
The v0 migration moves historical `chart.animation` and `chart.selection`
objects to their current top-level sections and normalizes legacy
`inside`/`outside` logo positions. Files declaring a newer unsupported schema
are rejected instead of being interpreted with potentially incorrect defaults.

`Project Studio` is a local Streamlit interface for creating and editing these
JSON files from a CSV. It can open existing files from `projects/*.json`,
inspect columns, derive new-project names and output paths from the selected
CSV filename, save a project file, render a selected year or transition preview
frame, and launch the final video render with visible progress. When it
edits an existing file, it preserves advanced JSON fields that are not exposed
in the form yet.

Project Studio keeps the current form as an in-memory draft. `Save project` is
an explicit action, and the status below the action buttons reports whether the
draft is saved or has unsaved changes. Rendering a preview or final video saves
the current draft first so the renderer always consumes the same JSON that the
editor displays. The latest preview stays visible across normal widget reruns
and is marked as out of date when the draft changes.

The active CSV is loaded through a bounded Streamlit data cache keyed by its
resolved path, size, and modification time. Column inspection, period metrics,
category editing, and the dataset table share that DataFrame instead of reading
the file separately on every rerun. Replacing a CSV at the same path
automatically invalidates the cached entry.

The category editor is designed for large datasets. It provides search,
filters for customized or missing-logo entries, and pages of 10, 20, or 40
rows instead of mounting every category widget at once. Row controls are
grouped in a form: edit the current page and select `Apply category changes`
before changing its search, filter, or page. Applied pages remain in the
session draft and are included when the project is saved, previewed, or
rendered. Bulk logo matching still evaluates every category, not only the
visible page.

The font picker, visual text-position editor, and live bar-appearance editor
use Streamlit Custom Components v2. They are controlled components: Python
rehydrates their current session value and the frontend emits named state with
`setStateValue`. They no longer use iframe messaging or the legacy components
v1 API. Component styles are isolated and consume Streamlit theme variables.

The bar editor exposes controls contextually. Simple mode shows only its
gradient plus shared border/projected-shadow controls. Advanced sections appear
for fill, texture, depth, effects, track, content, and frame, while dependent
fields remain hidden until their parent feature is enabled (for example bevel
size, glow details, second-logo layout, or value border settings). Inactive
values remain preserved in the project JSON.

Project Studio uses a dark creative-workspace layout configured natively in
`.streamlit/config.toml`; it does not inject fragile CSS into Streamlit. The
graphite surfaces, violet accent, Inter typography, visible widget borders,
compact heading scale, and independently styled sidebar remain consistent in
native widgets and CCv2 controls that consume Streamlit theme variables.

The main workspace is split into two responsive columns. The left editor uses
a segmented navigator for `Data`, `Canvas`, `Bars`, and `Export`, and mounts
only the selected section. This prevents unrelated panels from appearing after
a widget rerun and reduces the amount of UI rebuilt per edit. Values from
hidden sections are reconstructed from the current in-memory draft, so moving
between sections does not reset unsaved settings. The right stage keeps the
save, preview, and final-render actions close to the persistent preview, render
status, completed video, dataset snapshot, portable bundle action, and
generated JSON. On narrower windows the columns stack naturally. A compact
header identifies the project, destination JSON, dataset size, and saved/dirty
state without consuming the editing area.

The sidebar is the project library: open/new actions, portable ZIP import, and
CSV selection stay separate from the creative controls. Destructive project,
CSV, and bundle transitions use a focused unsaved-changes dialog. Advanced
fonts, sizes, colors, placement, materials, category details, preview-frame,
export, and output-path controls are collapsed until requested. The old
`Theme` and `Typography` selectors remain hidden because their individual
visual properties are editable; stored values remain compatible with older
project files.

The render settings show a live estimated video duration calculated from the
CSV's distinct time periods, steps per transition, motion mode, and FPS. The
same shared calculation supplies the pipeline's expected frame count, so the
displayed runtime matches the generated timeline. It describes final playback
length, not how long rendering will take.

Before a final render, Project Studio runs a preflight over the saved project,
data source, dataset columns and periods, FFmpeg, output path, background,
custom texture, and category-logo references. Errors block the render; missing
optional logos are warnings. A passing render starts in an isolated Python
process, reports progress from `output/.render_jobs/`, and can be canceled from
the UI. Cancellation terminates the worker and its FFmpeg child process.

Status and project JSON files use atomic temporary-file replacement with
bounded retries for transient Windows destination locks. Render-progress
updates are best-effort telemetry: if an external reader, antivirus, or indexer
briefly locks `status.json`, that update is skipped and logged instead of
terminating the video render. A later progress or terminal update restores the
visible status.

The worker writes FFmpeg output to a job-specific partial MP4 and atomically
replaces the configured video only after successful completion. A failed or
canceled run therefore does not overwrite the previous good video. Project
JSON saves use the same temporary-file-and-replace strategy. Loading another
project, starting a new one, or replacing a new-project CSV asks for explicit
confirmation when the current draft has unsaved changes.

Example:

```json
{
  "schema_version": 1,
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
    "bar_shape": "capsule",
    "bar_appearance_mode": "simple",
    "bar_border_enabled": true,
    "bar_border_color": "#FFFFFF",
    "bar_border_width": 1.5,
    "bar_shadow_enabled": true,
    "bar_shadow_color": "#000000",
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
entry can define a display `label`, a bar `color`, a primary `logo`, an optional
`secondary_logo`, or any combination of those fields:

```json
"categories": {
  "Gas": {
    "label": "Natural gas",
    "color": "#F28E2B",
    "logo": "logos/gas.png",
    "secondary_logo": "logos_secondary/gas.png"
  },
  "Solar": {
    "color": "#EDC948",
    "logo": "logos/solar.png"
  }
}
```

If a category has no custom color, the renderer keeps using the active theme
palette.

## Portable Project Bundles

Project Studio can prepare a `.barchart.zip` file from the current draft. The
bundle contains:

- the versioned project JSON;
- the CSV or SQLite data source;
- the selected background image and custom texture;
- all primary and secondary category logos;
- a manifest with the size and SHA-256 checksum of every included file.

Asset names are deduplicated and all paths inside the bundled JSON are portable.
On import, BarChartStudio validates the ZIP paths, rejects symbolic links,
encrypted entries, unexpected files, suspicious compression ratios, oversized
archives, and checksum mismatches before writing anything. Imported assets are
stored under `projects/imported/<project>/`, while the openable project JSON is
created under `projects/`. A second import receives a suffix such as `_2`; it
never silently overwrites an existing project.

The imported project's video and frame outputs are reset to unique paths under
`output/`. Bundle schema version 1 has a 512 MB compressed/uncompressed safety
limit and a maximum of 2,000 files.

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

Bars support four reusable shapes without changing the underlying race layout:

- `rectangle` keeps the classic square bar.
- `rounded` adds restrained corner rounding.
- `capsule` rounds both ends completely.
- `lollipop` uses a thin stem ending in a circle.

Set the shape with `bar_shape`. A configurable outline works with every shape:

```text
bar_border_enabled
bar_border_color
bar_border_width
```

Bars can also render a subtle configurable shadow behind the selected shape.
This is controlled in `ChartConfig` or in external project files:

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

When disabled, bars fall back to a solid fill while preserving the selected
shape, border, and shadow.

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

Each project can override the theme background from Project Studio's
`Background` panel. `Color` mode stores a custom canvas color. `Image` mode can
upload PNG, JPEG, or WebP files into `backgrounds/` and supports `Cover`,
`Contain`, and `Stretch` fitting. The selected color remains behind transparent
pixels and the margins produced by `Contain`. The image is resized once when
the renderer initializes and is then reused for every animation frame.

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
- deterministic simple/advanced renderer image signatures
- real render integration test with FFmpeg

GitHub Actions runs the locked dependency install, `pip check`, FFmpeg/FFprobe
checks, the environment doctor, compilation, the full unit/integration suite,
and the pixel-exact renderer references on `windows-latest` with Python 3.13.

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
    artists.py
    bar_renderer.py
    text_compositor.py
  studio/
  ui/
  utils/
  validators/
  main.py

projects/
tests/
```

The renderer is split at stable visual boundaries. `artists.py` owns reusable
Matplotlib image artists, `text_compositor.py` owns rasterized text and its
caches, and `bar_renderer.py` remains the scene/bar coordinator. In the UI,
`render_workflow.py` owns preflight, background-process progress, cancellation,
status, and render-profile presentation so `project_studio.py` can focus on the
editor form and draft state.

Two pixel-exact regression fixtures cover the Simple and Advanced appearance
paths. If an intentional renderer change alters either signature, inspect the
new frame first and update the reference hash in the same reviewed change.

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

### Frame output modes

`chart.frame_output_mode` controls how rendered frames reach FFmpeg:

- `ffmpeg_stream` (default and recommended) draws RGBA frames in memory and
  writes them directly to FFmpeg stdin, avoiding PNG encoding and temporary
  frame files.
- `png_sequence` preserves the PNG-frame pipeline as an optional fallback when
  individual frames need to be inspected or reused.

`png_compress_level` only applies to `png_sequence`. Level `0` saves faster and
uses more disk space, while level `9` produces smaller intermediate files more
slowly. It does not change the MP4 image quality.

The renderer keeps its Matplotlib figure and artists alive for the full job;
subsequent frames update bars, borders, shadows, logos, labels, and headers in
place. Enabled bar gradients are batched into one reusable color-segment
collection instead of creating and resampling one bicubic image per visible
bar. Curved shapes add detail only around their rounded regions.

The `Bar appearance` panel in Project Studio combines shape cards with a live
preview and controls for gradient, border, shadow color, opacity, width, and
offset. The selected values are stored in the project JSON.

`Bar appearance` has two modes:

- `Simple` preserves the optimized solid/gradient renderer and the original
  border and projected-shadow controls.
- `Advanced` builds a cached RGBA material per category and composites shape,
  fill, texture, depth, shine, and border into compact per-bar sprites that are
  sent directly to Agg through one reusable artist. Tracks, projected shadows,
  and glow are batched into three global vector collections so their layer order
  remains correct while bars cross. Text stays as an independent sharp layer;
  logos use their own direct sprite compositor. It exposes tabs for Fill,
  Texture, Depth, Effects, Track, Content, and Border & shadow.

Advanced Fill supports solid, gradient, or textured materials; horizontal,
vertical, and diagonal gradients; two or three color stops; movable highlight;
and edge darkening. Category colors can remain authoritative or be replaced by
custom start, center, and end colors.

Texture presets include noise, brushed metal, grunge, paper, carbon, and a
custom image path. Texture intensity, scale, contrast, and Overlay, Multiply,
Screen, or Soft Light blending are configurable. Relative custom paths are
resolved from the directory where BarChartStudio is launched. Project Studio
can also upload PNG, JPEG, or WebP textures into the local `textures/` folder.

Depth and lighting are separate layers:

```text
bar_bevel_enabled
bar_bevel_size
bar_bevel_highlight_opacity
bar_inner_shadow_opacity
bar_inner_shadow_size
bar_top_highlight_opacity
bar_bottom_shade_opacity
bar_outer_glow_enabled
bar_glow_color
bar_glow_opacity
bar_glow_blur
bar_inner_glow_opacity
bar_shine_enabled
bar_shine_position
bar_shine_width
bar_shine_opacity
```

The projected `bar_shadow_*` controls remain exclusively responsible for the
shadow behind the bar. They do not modify bevel, inner shadow, or glow.

Advanced materials intentionally cost more to rasterize, but the compositor
reduces that cost for every Advanced combination. In the same repeated
eight-bar 1920x1080 A/B check, Advanced Fill improved from `0.1367s/frame` to
`0.0983s/frame` (about 28%), while the fully layered texture/depth/glow sample
improved from `0.1570s/frame` to `0.1296s/frame` (about 17%). Materials, resized
fills, antialiased shape masks, border masks, prepared logos, and composed logo
sprites use bounded caches.

On the real 457-frame national-team cumulative project with capsule bars,
inside-right flags, projected shadows, and direct FFmpeg streaming, total time
fell from `100.213s` to `57.146s`. Draw time fell from `96.494s` to `54.601s`,
about a 43% reduction, while MP4 export remained below one second. Simple is
still the fastest choice, but Advanced no longer creates one clipped
Matplotlib image plus multiple effect patches for every visible bar.

Static background images use a direct Agg artist after `cover`, `contain`, or
`stretch` is resolved once at canvas size. This avoids sending the same full-HD
image through Matplotlib's `AxesImage` resampler on every frame. With the same
457-frame project, 316 matched logos, Advanced capsule bars, and a full-canvas
JPEG background, total time fell from `206.162s` to `67.430s`; draw time fell
from `202.250s` to `64.714s`, about a 68% reduction.

Visible logos are also composed once per file, target size, mask, background,
and border combination. One direct Agg command list replaces each logo's former
Matplotlib image, clip patch, background patch, and border patch. This applies
to Simple and Advanced modes and preserves outside-left, inside-left,
inside-right, hidden, square, rounded, circle, and adaptive behavior. On the
same 457-frame background-image project, this reduced total time again from
`67.430s` to `57.022s` and draw time from `64.714s` to `54.297s`.

Advanced Track can draw a full-width background bar behind each value. Content
controls can place logos outside-left, inside-left, inside-right, or hide them.
Logo masks can follow the bar automatically or use circle, rounded, or square
shapes, with independent padding, background, opacity, border color, and border
width. A category can also have a second logo displayed as an overlaid badge,
beside the primary logo, or in an independent inside/outside position. Its
size, shape, gap, padding, background, and border are configured separately.
Capsule and lollipop logos use circular adaptive masks; an inside-left
lollipop logo adds a circular socket at the start of the stem, while an
inside-right logo occupies its endpoint circle. Legacy `outside` and `inside`
project values remain supported and are migrated by the editor. Category
labels can be placed left, inside, above, or outside, and values automatically,
outside, inside, or above. Inside labels and values reserve the selected logo
slot. Category text alignment is independent from position and supports Auto,
Left, Center, and Right within the category's existing text area. Value color,
outline, and shadow are configurable, while font family and size remain
synchronized with the existing text controls.

Project Studio offers up to 30 curated common font families installed on the
current system and allows independent selection for the title, subtitle,
category labels, values, date, source, and ranking. Each dropdown renders its
font name and `Aa 123` sample using that family. `Project default` inherits the
base font retained by the project.

The `Text colors` panel provides independent color controls for the title,
subtitle, category labels, values, date, source, and ranking. Older projects
without these fields continue to inherit their original theme colors. An
explicit category or value color also applies when that text is placed inside
a bar; the automatic contrast color remains active when no override exists.

The `Text sizes` panel exposes independent point sizes for all seven text
elements. The visual text-layout editor lets users drag title, subtitle, date,
and source directly on a scaled canvas. It supports arrow-key nudging,
horizontal alignment, safe-area guides, and preset reset while persisting X/Y
coordinates internally.

### Motion modes

Project Studio exposes two animation modes:

- `Per-year easing` preserves the original independent easing for every pair
  of years.
- `Continuous` uses neighboring yearly keyframes to keep bar positions,
  widths, rankings, and smoothed values moving through year boundaries without
  restarting velocity. Boundary frames are emitted once instead of duplicated.

The source data remains annual; continuous mode only changes interpolation and
does not invent monthly observations.

The streaming mode can also be selected from Project Studio or overridden from
the CLI:

```powershell
python src/main.py --project projects/example.json --frame-output-mode ffmpeg_stream
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

After a successful Project Studio render, the persistent result card includes
an embedded video player, the final path and size, the render profile, and an
MP4 download button. Videos larger than 200 MB remain playable from disk but
are not duplicated into Streamlit's in-memory download buffer.

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
    "logo": "logos/coal.png",
    "secondary_logo": "logos_secondary/coal.png"
  }
}
```

Project Studio can upload a complete logo folder, choose an existing file from
a logo folder, auto-match files whose names match category names, or upload a
logo for a category. The same workflow is available independently for the
second logo. Uploaded primary folders are copied under `logos/`, secondary
folders under `logos_secondary/`, and both category paths are referenced from
the project JSON.
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

- The consolidation roadmap is complete. Keep future work driven by concrete
  chart types or user workflows, preserving the schema, bundle, renderer, and
  regression contracts documented above.
