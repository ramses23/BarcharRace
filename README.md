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
- Draw the large time label as a background watermark behind chart content,
  with configurable 0–100% opacity (22% by default).
- Auto-fit visible bars to the available vertical layout space.
- Choose legacy manual bar rows or a reactive `fill_available` vertical layout
  that reserves only visible title, subtitle, and source layers; the date
  watermark never consumes bar-row space.
- Place category labels outside-left, inside-left, inside-center, inside-right,
  or outside-right with independent X/Y offsets and logo/value collision guards.
- Apply reusable layout presets for common video formats.
- Apply configurable font weights and max widths to title, subtitle, time
  label, and source label.
- Apply reusable typography presets.
- Render rectangle, rounded, capsule, and lollipop bar shapes.
- Render independent projected shadows, borders, gradients, textures, depth,
  glow, shine, and background tracks through one unified appearance editor.
- Resolve and render optional logos for bars.
- Export PNG frames to MP4 with configurable FFmpeg quality options.
- Report render progress through a reusable `RenderJob` callback.
- Run project presets from the command line.
- Override preset render options from the command line.
- Render external JSON project files.
- Keep application code and user-owned productions in separate filesystem
  roots through Workspace Separation V1.
- Create, open, edit, and preview project files from a local Streamlit editor.
- Preview a selected year or transition point before rendering a full video.
- Automatically refresh previews after visual Canvas, Bars, category, or
  preview-frame changes without saving the in-memory draft.
- Render project-specific source labels instead of raw local file paths.
- Apply project-specific category labels and bar colors.
- Tune the category-label boundary, bar start, and usable label-area span from
  Project Studio without editing JSON manually.
- Assign project-specific category logos from the local Streamlit editor.
- Export/import complete project bundles with data and visual assets.
- Play and download the finished MP4 directly from Project Studio.
- Limit large frames with configurable top-N selection and optional "Other".
- Precompute per-year sprites so transitions reuse prepared layout state.
- Report per-stage render profiling timings for larger-dataset tuning.
- Apply an application-wide soft render CPU ceiling (enabled at 95% by
  default, 50–100%; 100% is unlimited) with cooperative frame throttling and
  bounded FFmpeg threads. This preference lives in the local application
  settings, not in portable project JSON.
- Compose fun facts as the original `right_panel`, the stable
  `editorial_right` column, or a movable `editorial_floating` card. Floating
  cards can be vertical or horizontal and configure their canvas rectangle,
  image side, bar safety gap, typography, image fit/area, and
  transparent/solid/card background.
- Run a complete local production from a strict version-2 brief, including
  dataset construction, optional local logos, project assembly, preflight, and
  an isolated MP4 render.
- Run a minimal automated test suite with `unittest`.

## Requirements

- Python 3.13
- FFmpeg available in `PATH`
- Exact Python packages from the locked `requirements.txt`

The project already expects a local virtual environment at `.venv`.

## Application And Workspace Separation

BarChartStudio uses three explicit roots:

- `APP_ROOT` is the Git checkout. It owns `src/`, `tests/`, official presets,
  examples, documentation, and small tracked fixtures.
- `WORKSPACE_ROOT` is external user storage. On a first run without settings,
  it defaults to a sibling named `<APP_ROOT name>Workspace`.
- `PRODUCTION_ROOT` (also the `project_root` for its projects) is one
  self-contained directory under `WORKSPACE_ROOT/productions/<slug>/`.

On Windows, the selected workspace is persisted atomically in:

```text
%LOCALAPPDATA%/BarChartStudio/settings.json
```

The same application settings file stores the render CPU preference. Existing
Workspace Separation V1 files containing only `schema_version` and
`workspace_root` remain valid and receive the default 95% soft ceiling in
memory until the preference is explicitly saved.

The location can be changed or initialized from the native `Workspace` panel
in Project Studio. A V1 workspace contains only these shared directories:

```text
BarChartStudioWorkspace/
  productions/
  scratch/
  packages/
  cache/
```

A production owns its project definitions, inputs, assets, editorial content,
and outputs. Directories are created only when needed:

```text
productions/mobile_usage/
  production.json
  data/
  projects/race_01.json
  assets/logos/
  assets/flags/
  assets/photos/
  assets/backgrounds/
  fun_facts/
  output/previews/
  output/races/
  output/master/
  generated/
```

Paths inside a production project are portable and resolve from that
production root. For example, `data/race_01.csv`, `assets/logos`,
`assets/backgrounds/main.png`, and `fun_facts/race_01.json` all remain inside
the same production. `..`, drive-relative paths, symlink/junction escapes, and
user-content writes into `APP_ROOT` are rejected.

Standalone work begins under `WORKSPACE_ROOT/scratch/`. Tracked examples and
legacy files under `APP_ROOT/projects/` remain readable, are labeled explicitly
as `Example` or `Legacy`, and are cloned into scratch on their first save. No
existing local data is moved automatically.

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
.venv\Scripts\python.exe src\main.py `
  --workspace D:\path\to\BarChartStudioWorkspace `
  --production-root D:\path\to\BarChartStudioWorkspace\productions\mobile_usage `
  --project D:\path\to\BarChartStudioWorkspace\productions\mobile_usage\projects\race_01.json
```

Tracked legacy examples remain runnable. Their inputs are read from
`APP_ROOT`, while their generated output is redirected to workspace scratch:

```powershell
.venv\Scripts\python.exe src\main.py --project projects/sample_project.json
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
| `--workspace` | override the configured external workspace root |
| `--production-root` | root for project-relative data, assets, and outputs |
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

All referenced paths must remain below the explicit production `--root`. Each
job reserves `generated/production_jobs/<job_id>/` exclusively and never
overwrites an older job. The principal results are:

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

Project Studio discovers projects first under workspace productions and
scratch. A generated production project can be opened in place; it no longer
needs an editable copy under the repository. Repository projects are listed as
read-only legacy entries and are cloned to scratch when saved.

The Project Library selector keeps each portable path as its internal identity
but displays the meaningful project name first, for example
`most_used_web_browsers — Production`. Duplicate stems add their production,
scratch, example, or legacy context deterministically. The selected full name,
location kind, and portable relative path appear immediately below the selector.

This MVP is intentionally local and single-job. It has no automatic downloads,
remote logo discovery, scheduler or queue, retry/resume recovery, cloud
publication, or new automation UI. See `production/README.md` for the complete
example and brief format.

## Project Files

External project files are JSON documents. They let you create new videos
without editing Python source files.

The current project schema is version `2` and new files include
`"schema_version": 2`. Existing unversioned files are schema `0`: they are
migrated in memory when opened and written back as version 2 on the next save.
The v0 migration moves historical `chart.animation` and `chart.selection`
objects to their current top-level sections and normalizes legacy
`inside`/`outside` logo positions. Files declaring a newer unsupported schema
are rejected instead of being interpreted with potentially incorrect defaults.

`Project Studio` is a local Streamlit interface for creating and editing these
JSON files from a CSV. It opens workspace production and scratch projects in
place, displays tracked examples and repository projects as explicit read-only
sources, inspects columns, derives new-project names and output paths, renders
previews, and launches final video renders with visible progress. New uploads,
projects, previews, assets, job state, and renders are written to the active
production or scratch root, never to the Git checkout. Existing advanced JSON
fields that are not exposed in the form are preserved.

Project Studio keeps the current form as an in-memory draft. `Save project` is
an explicit action, and the status below the action buttons reports whether the
draft is saved or has unsaved changes. Manual preview and final-video actions
save the current draft first so the renderer consumes the same JSON that the
editor displays.

`Auto preview` is enabled by default. After the first visual edit, it renders
the current draft directly from memory without writing the project JSON.
Changes in `Canvas`, `Bars`, `Fun facts`, applied category styles, or the selected preview
frame trigger it; `Data` and `Export` changes do not. Disabling the toggle
pauses automatic work, and enabling it again renders one pending visual update.
The latest preview stays visible across normal widget reruns. A separate
preview fingerprint marks it stale only when a render-relevant change remains
outside the automatic visual scope.

The collapsed `Appearance presets` panel saves the current `Canvas`, `Bars`,
and `Fun facts` appearance as a reusable local preset. Enter a unique name and choose
`Save new preset`; in another project, select that preset and choose `Apply
preset`. `Update preset` replaces the selected preset with the current visual
settings, while deletion requires confirmation. Applying a preset updates the
in-memory draft and automatic preview but never saves the project JSON.

Appearance presets use the independent versioned contract
`appearance-preset-v5` and remain under the app-owned
`APP_ROOT/presets/appearance/` library. Existing V1–V4 presets remain
loadable. Older files receive compatible defaults for fields that did not yet
exist: date opacity remains the legacy `0.22`, every other text opacity is
fully opaque, card texture is `none`, and floating-card geometry retains its
previous defaults.
They include canvas layout, background, typography, text visibility and
placement, value formatting, every bar-appearance control, and Fun Fact panel,
fade, and editorial styling. They exclude project content and behavior:
title/source text, Fun Fact enabled/source/content, dataset columns, category
colors and logos, Top N, animation, output paths, and export settings remain
those of the destination project. The JSON files are ignored by Git so local
personal presets are not committed accidentally; copy a preset file explicitly
when it needs to be shared with another installation.

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

The expanded `Canvas -> Category and bar geometry` panel exposes three compatible
layout fields:

- `Category label start` writes `chart.label_min_x`;
- `Bar start` writes `chart.left_margin`;
- `Category area span` writes `chart.rank_label_gap`.

`Use full left space` calculates the span required to keep the ranking column
at the preset's `rank_label_min_x` while allowing category names to use the
otherwise empty area before the bars. Values are bounded by the selected
canvas, persist in project JSON, and fall back to the layout preset for older
projects that do not contain the fields.

The expanded `Canvas -> Text visibility` panel can independently show or hide
the title, subtitle, large date, source, rankings, category names, and values.
These choices are stored in the project JSON, participate in automatic preview
updates, and leave typography and placement settings intact so an element can
be restored without reconfiguring it. Older projects remain fully visible
because every visibility field defaults to `true`.

`Canvas -> Text colors and opacity` exposes independent base opacity for title,
subtitle, date, and source. `Bars -> Bar text colors and opacity` does the same
for category, value, and ranking text, while `Fun facts -> Editorial layout ->
Editorial text` controls headline, body, and credit. Values are stored from
`0.0` to `1.0`; older projects remain visually identical because every new
field defaults to `1.0` except the historical date watermark, which remains
`0.22`. The effective renderer alpha is `configured opacity × animation/fade
opacity`, so transitions still work without overwriting the chosen base value.
The same settings drive the in-memory preview, saved JSON, final renderer, Text
Placement representation, and appearance presets.

The font picker, visual text-position editor, editorial-card editor, and live bar-appearance editor
use Streamlit Custom Components v2. They are controlled components: Python
rehydrates their current session value and the frontend emits named state with
`setStateValue`. They no longer use iframe messaging or the legacy components
v1 API. Component styles are isolated and consume Streamlit theme variables.

Text Placement V2 builds the selected preview frame with the normal
`Timeline`, `BarSelector`, `LayoutEngine`, and Fun Fact layout, then converts
the resulting scene to final-canvas-pixel geometry in Python. The frontend only
scales and draws real row/bar extents, ranking/category/value lanes, text
bounds, logo slots, editorial and collision rectangles. Title, subtitle, date,
and source keep drag, keyboard nudge, alignment, and preset reset. When the
editorial layout owns the date position, the editor shows that effective
position and marks it as managed instead of saving an overridden coordinate.

`Fun facts -> Editorial layout -> Position and size` retains exact X/Y/width/
height number inputs and adds a controlled visual card editor. Drag the card
body to move it or use its eight edge/corner handles to resize. Interaction is
local while dragging and emits one update on pointer release; arrow keys move
1 canvas pixel and Shift+arrows move 10. Both input directions use final-canvas
pixels, shared minimum dimensions, and clamping that keeps the whole card
inside the canvas. The editor reuses the same Python scene overlays as Text
Placement. Gesture events carry a unique component-instance id and the geometry
from which the gesture started. Python consumes each event once and accepts it
only when that base still matches the current draft, which prevents stale
events and keeps a remounted component responsive after section changes. An
unrelated rerun during a drag does not replace the active DOM or pointer
capture.

The bar editor exposes one contextual model for fill, texture, depth, effects,
track, category text, content, and frame. Dependent fields remain hidden until
their parent feature is enabled (for example bevel size, glow details,
second-logo layout, or value border settings), and active-setting chips make
the effective combination visible. The frontend writes one unified state;
backend selection is automatic.

Project Studio uses a dark creative-workspace theme configured natively in
`.streamlit/config.toml`; colors, typography, borders, and widget styling do
not depend on injected CSS. An invisible CCv2 layout controller watches the
stable `latest_preview` container. Once that card reaches the workspace header,
the controller anchors it to the viewport, keeps a placeholder in the original
flow, and synchronizes its width and horizontal position with the stage column.
Below 900 px it restores the normal stacked document flow.

The main workspace is split into two responsive columns. The left editor uses
a segmented navigator for `Data`, `Canvas`, `Bars`, `Fun facts`, and `Export`, and mounts
only the selected section. This prevents unrelated panels from appearing after
a widget rerun and reduces the amount of UI rebuilt per edit. Values from
hidden sections are reconstructed from the current in-memory draft, so moving
between sections does not reset unsaved settings. The right stage keeps the
save, preview, and final-render actions close to the persistent preview, render
status, completed video, dataset snapshot, portable bundle action, and
generated JSON. On narrower windows the columns stack naturally. A compact
header identifies the project, destination JSON, dataset size, and saved/dirty
state without consuming the editing area.

Within that stable navigator, controls are grouped as project identity/column
mapping/source in Data; canvas/background, available content area, geometry,
and typography in Canvas; selection/visible rows and appearance in Bars;
source/scheduling, card layout, editorial style, position/size, and preview in
Fun Facts; and motion/duration, encoding, and output in Export. Existing widget
keys and the `CURRENT_DRAFT_STATE` bridge remain unchanged so switching sections
does not discard unsaved values. Workspace CPU preferences are visually
separated from workspace location controls, and appearance presets remain in a
collapsed panel.

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
data source, dataset columns and periods, fun fact schedule/assets, FFmpeg,
output path, background, custom texture, and category-logo references. Errors block the render; missing
optional logos are warnings. A passing render starts in an isolated Python
process, reports progress from `WORKSPACE_ROOT/cache/render_jobs/`, and can be
canceled from the UI. Cancellation terminates the worker and its FFmpeg child
process.

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
  "schema_version": 2,
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
    "title_enabled": true,
    "subtitle_enabled": true,
    "time_label_enabled": true,
    "source_label_enabled": true,
    "rank_labels_enabled": true,
    "category_labels_enabled": true,
    "value_labels_enabled": true,
    "rank_label_prefix": "#",
    "rank_label_min_x": 96,
    "rank_label_label_gap": 18,
    "label_min_x": 40,
    "value_label_gap": 16,
    "value_label_min_x": null,
    "auto_fit_bar_count": true,
    "max_visible_bars": null,
    "bar_shape": "capsule",
    "bar_appearance_mode": "unified",
    "bar_fill_type": "gradient",
    "bar_gradient_direction": "horizontal",
    "bar_gradient_color_count": 2,
    "bar_fill_use_category_color": true,
    "bar_edge_darkening": 0,
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
  "fun_facts": {
    "enabled": false,
    "layout": "right_panel"
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
| `fun_facts` | optional timeline-bound editorial overlay configuration |

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

## Fun Fact Overlay System

Fun Fact Overlay System V1 draws an editorial card inside the same PIL and
Matplotlib render pipeline as the bar chart. Bars continue moving while the
card fades in and out; enabling the feature does not add frames, change FPS,
or change the estimated or rendered playback duration. V1 permits one active
fact at a time. Editorial Layout V2 adds `editorial_floating` without changing
the independent version-1 fact-content contract or the version-2 project
schema.

The engine only validates, schedules, packages, and renders facts supplied by
the project. It does not select editorial facts, search for images, download
assets, or depend on a particular topic. Topic-specific datasets, copy, and
licensed local images belong to separate production packages, not to `src/`.

The project references one external, versioned JSON file:

```json
"fun_facts": {
  "enabled": true,
  "source": "fun_facts/fun_facts.json",
  "layout": "right_panel",
  "panel_width": 520,
  "panel_margin": 32,
  "panel_padding": 28,
  "fade_in": 0.2,
  "fade_out": 0.2
}
```

When `panel_width` is omitted, the panel uses 28 percent of the canvas width.
The panel plus its margins are reserved for the entire video, including frames
without an active fact. Bar width, outside value labels, title, subtitle,
source, and the large time label therefore remain inside a stable data area
instead of being covered when a card appears.

`editorial_right` keeps the same stable right-column behavior with additional
editorial typography and background controls. `editorial_floating` instead
uses an explicit rectangle and does not reserve a full-height column:

```json
"fun_facts": {
  "enabled": true,
  "source": "fun_facts/fun_facts.json",
  "layout": "editorial_floating",
  "panel_padding": 28,
  "editorial_orientation": "horizontal",
  "editorial_card_x": 900,
  "editorial_card_y": 520,
  "editorial_card_width": 900,
  "editorial_card_height": 360,
  "editorial_image_position": "right",
  "editorial_collision_gap": 24,
  "editorial_background_mode": "card",
  "editorial_background_color": "#111827",
  "editorial_background_texture": "paper",
  "editorial_background_texture_intensity": 0.2,
  "editorial_headline_opacity": 1.0,
  "editorial_body_opacity": 0.9,
  "editorial_credit_opacity": 0.75
}
```

Card backgrounds support `none`, `grain`, `paper`, `dots`, and `diagonal`
textures. The texture modifies material detail without replacing the selected
background color, and its intensity can be set from 0% to 100%. Transparent
background mode deliberately ignores the texture. Project Studio's card editor,
Latest Preview, and final render use the same stored choice and deterministic
material generator.

The layout engine intersects that rectangle with each visible bar row. It
reserves the measured outside-value lane only on the affected vertical band,
then derives one common pixels-per-value scale for every bar. Rows above or
below the card can therefore extend into the otherwise free space, while
intersecting rows keep bars, inside logos, and outside/automatic values clear
of the card. The common scale preserves honest proportional comparison and
remains stable through rank transitions.

The referenced `fun_facts.json` uses this independent version-1 contract:

```json
{
  "version": 1,
  "fun_facts": [
    {
      "id": "milestone_2012",
      "start": "2012-06",
      "end": "2012-11",
      "headline": "A NEW MILESTONE",
      "body": "The selected series reached a notable point in this interval.",
      "image": "fun_facts/images/milestone.jpg",
      "layout": "right_panel",
      "accent_color": "#3B82F6",
      "image_fit": "cover",
      "credit": "Photo: Local licensed asset"
    }
  ]
}
```

`id`, `start`, `end`, and `headline` are required. `body`, `image`,
`accent_color`, and `credit` are optional. Images may be PNG, JPEG, or WebP;
EXIF orientation is applied before a cached `cover` or `contain` resize. Paths
in both JSON files are relative to the project root, which also makes them
portable through production packages.

Scheduling uses dataset timeline labels, not MP4 seconds. For a traditional
annual dataset without `dataset.time_label_column`, labels fall back to
`str(period)`, so `"start": "2012"` resolves to numeric period 2012. A monthly
dataset can keep a numeric interpolation axis and a separate visible label:

```json
"dataset": {
  "year_column": "period",
  "time_label_column": "date",
  "name_column": "brand",
  "value_column": "value"
}
```

For rows such as `period=2,date=2010-05`, a fact scheduled at `2010-05`
resolves to internal period 2. Both transition previews and continuous-motion
renders use the interpolated ordinal timeline position for fade opacity.
Duplicate display labels, unresolved boundaries, reversed ranges, and
overlapping facts are rejected rather than assigned ambiguous priority.

Project Studio exposes `Fun facts` as its own editor section. It can enable or
disable the system, select the JSON source, configure geometry and fades, show
the fact count and date range, choose a preview period, force a selected fact
for design review, or return to normal timeline scheduling. Final-render
preflight reports the fact id, field, and resolved path for invalid JSON,
missing images, unsupported layouts/fits, unresolved dates, overlaps, or panel
geometry that leaves no useful chart area.

For `editorial_floating`, the editor exposes card orientation, X/Y position,
width/height, image side, and a bar/card safety gap. These controls participate
in auto preview, project persistence, portable bundles, and V5 appearance
presets; content fields such as the enabled state, source JSON, and fact copy
remain project-specific.

## Portable Project Bundles

Project Studio can prepare a `.barchart.zip` file from the current draft. The
bundle contains:

- the versioned project JSON;
- the CSV or SQLite data source;
- the selected background image and custom texture;
- all primary and secondary category logos;
- the fun fact JSON and every referenced local fact image;
- a manifest with the size and SHA-256 checksum of every included file.

Asset names are deduplicated and all paths inside the bundled JSON are portable.
On import, BarChartStudio validates the ZIP paths, rejects symbolic links,
encrypted entries, unexpected files, suspicious compression ratios, oversized
archives, and checksum mismatches before writing anything. A valid package is
staged under workspace cache and atomically installed as a self-contained
`WORKSPACE_ROOT/productions/<slug>/`; its editable JSON remains at
`projects/<slug>.json` inside that production. A second import receives a
suffix such as `_2` and never silently overwrites an existing production.

The imported project's video and frame outputs are reset to production-relative
paths under `output/races/` and `output/frames/`. Package bindings use schema 2
with portable `production_reference` and `project_relative_path` fields; schema
1 repository bindings remain readable for backward compatibility. Bundle
schema version 1 has a 512 MB compressed/uncompressed safety limit and a
maximum of 2,000 files.

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

All renderer text layers have independent visibility flags:

```text
title_enabled
subtitle_enabled
time_label_enabled
source_label_enabled
rank_labels_enabled
category_labels_enabled
value_labels_enabled
```

They default to `true`. Project Studio exposes them in `Canvas -> Text
visibility`, and disabled layers are omitted from both preview frames and final
video frames.

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

The title uses all remaining canvas width by default, from `title_x` (or the
layout's left margin) to the safe right edge. Set `title_max_width` to a number
only when a narrower title column is intentional. The title, subtitle, and
source label are truncated with `...` only when they exceed their effective
width or the remaining canvas width.

Available typography presets:

| Preset | Notes |
|---|---|
| `studio` | Default balanced text scale |
| `editorial` | Larger title/subtitle scale for polished 1080p videos |
| `compact` | Smaller text scale for denser charts |

## Text Fitting

Bar labels and value labels use measured collision handling.

The renderer measures text with Pillow using the same effective font file,
fallback family, weight, point size, and render DPI used for the final frame.
A complete category name is preserved whenever its measured pixels fit.
Otherwise a binary search finds the longest prefix that fits together with
`...`; the ellipsis is never appended unless truncation is required. This
works with accented characters, spaces, different font families, and different
canvas resolutions.

The available category width is calculated from the ranking column, configured
label boundary, bar start, logo placement, logo gaps, and category alignment.
This keeps names out of the logo and bar while avoiding premature truncation.
Value labels are drawn outside the bar when they fit, moved inside the bar when
the right edge would overflow, or clamped to a safe right edge when the bar is
too small. Very large value labels are measured and truncated inside the safe
value-label area instead of stretching into the left label column.

The large time label is rendered as a low-opacity background watermark behind
bars and source text, which keeps dense layouts readable.

`text_average_char_width` remains accepted for compatibility with callers that
do not provide a font, but renderer fitting uses real glyph measurement.

Text fitting is configured in `ChartConfig`:

```text
title_max_width
subtitle_max_width
source_max_width
label_min_x
left_margin
rank_label_gap
rank_label_min_x
rank_label_label_gap
text_average_char_width
value_label_gap
value_label_edge_padding
value_label_min_x
value_label_inside_padding
value_label_inside_color
```

`title_max_width` defaults to `null`, which means automatic remaining-width
fitting. A positive numeric value remains supported as an explicit cap for
project-specific compositions.

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
- real-font text fitting for title, subtitle, source, rank-aware bar labels,
  ellipsis placement, and value-label layout
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
- automatic visual preview scope, pause/resume behavior, and unsaved in-memory
  preview rendering
- category-label boundary, bar-start, and label-area persistence
- category labels and colors from project files
- explicit category logo paths from project files
- deterministic legacy Simple/Advanced renderer signatures plus unified
  vector-renderer equivalence
- real render integration test with FFmpeg

GitHub Actions runs the locked dependency install, `pip check`, FFmpeg/FFprobe
checks, the environment doctor, compilation, the full unit/integration suite,
and the pixel-exact renderer references on `windows-latest` with Python 3.13.

## Architecture

Filesystem context is resolved before the render pipeline starts:

```text
APP_ROOT (software/resources, read during normal use)
  + WORKSPACE_ROOT (user content)
      + PRODUCTION_ROOT or scratch project root (project_root)
          -> data/assets/fun facts
          -> previews/frames/MP4
```

`src/studio/workspace_paths.py` owns settings, discovery, classification, and
the explicit app-root write guard. `src/studio/project_runtime.py` resolves
portable input paths from `project_root` and constrains render paths to the
explicit `output_root`.

Current render pipeline:

```text
JSON project file or ProjectPreset
    -> ChartConfig
    -> FunFactConfig
    -> AnimationConfig
    -> ThemeConfig
    -> DataSourceConfig
    -> DatasetConfig
    -> RenderJob
        -> DataSourceLoader
        -> DatasetValidator
        -> Timeline
        -> FunFactScheduler
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

Pixel-exact regression fixtures cover both legacy appearance paths and verify
that the unified classic gradient remains identical to the optimized legacy
Simple result. If an intentional renderer change alters a signature, inspect
the new frame first and update the reference hash in the same reviewed change.

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
optional ActiveFunFact
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

The `Bar appearance` panel in Project Studio is one unified editor: there is no
Simple/Advanced selector and therefore no second set of settings that can stay
active invisibly. Shape, Fill, Texture, Depth, Effects, Track, Category text,
Content, and Frame controls share one normalized state. Contextual controls
appear only while their parent feature is active, and a compact chip summary
shows the active shape, fill, effects, logo placement, and value placement.
The live preview and collapsible groups preserve their open or closed state
while a field change rebuilds the component.

The renderer chooses its internal backend automatically. Category-color solid
fills and the classic two-stop horizontal gradient use the optimized vector
path. Textures, custom colors, multidirectional or three-stop gradients, depth,
glow, shine, and tracks activate the cached RGBA material compositor. This is
an implementation detail rather than a user mode: combining controls cannot
leave an alternate appearance profile hidden in the project.

Legacy project and appearance-preset JSON containing
`bar_appearance_mode="simple"` or `"advanced"` remains loadable and renders
unchanged. The editor presents either legacy representation through the unified
controls; the first bar-style edit writes `bar_appearance_mode="unified"` while
preserving the visible result. Untouched legacy files are not rewritten merely
by opening them.

Unified Fill supports solid or gradient materials; horizontal,
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

Material combinations intentionally cost more to rasterize, but the compositor
reduces that cost for every layered combination. In the same repeated
eight-bar 1920x1080 A/B check, material Fill improved from `0.1367s/frame` to
`0.0983s/frame` (about 28%), while the fully layered texture/depth/glow sample
improved from `0.1570s/frame` to `0.1296s/frame` (about 17%). Materials, resized
fills, antialiased shape masks, border masks, prepared logos, and composed logo
sprites use bounded caches.

On the real 457-frame national-team cumulative project with capsule bars,
inside-right flags, projected shadows, and direct FFmpeg streaming, total time
fell from `100.213s` to `57.146s`. Draw time fell from `96.494s` to `54.601s`,
about a 43% reduction, while MP4 export remained below one second. The editor
automatically keeps compatible styles on the faster vector path; layered
materials no longer create one clipped Matplotlib image plus multiple effect
patches for every visible bar.

Static background images use a direct Agg artist after `cover`, `contain`, or
`stretch` is resolved once at canvas size. This avoids sending the same full-HD
image through Matplotlib's `AxesImage` resampler on every frame. With the same
457-frame project, 316 matched logos, material capsule bars, and a full-canvas
JPEG background, total time fell from `206.162s` to `67.430s`; draw time fell
from `202.250s` to `64.714s`, about a 68% reduction.

Visible logos are also composed once per file, target size, mask, background,
and border combination. One direct Agg command list replaces each logo's former
Matplotlib image, clip patch, background patch, and border patch. This applies
to both internal render paths and preserves outside-left, inside-left,
inside-right, hidden, square, rounded, circle, and adaptive behavior. On the
same 457-frame background-image project, this reduced total time again from
`67.430s` to `57.022s` and draw time from `64.714s` to `54.297s`.

Track can draw a full-width background bar behind each value. Content
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

The compact text-color panels provide independent color and base-opacity
controls for title, subtitle, category labels, values, date, source, and
ranking. Older projects without these fields continue to inherit their original
theme colors and remain fully opaque except for the historical 22% date. An
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

Generated files are written under the active production or scratch root:

```text
<project_root>/output/previews/
<project_root>/output/races/
<project_root>/output/master/
<project_root>/output/frames/
```

Frame files use:

```text
<project_root>/output/frames/<project>/frame_0000.png
```

Before each render, old `frame_*.png` files are removed from the configured
frames directory so FFmpeg cannot mix old and new frames.

Repository `output/` remains ignored as a second defense for legacy/dev flows,
but the runtime guard and explicit workspace roots are the primary protection.

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

`libx264` exports use a closed, two-second GOP with one reference frame and no
B-frames, declare limited-range BT.709 color metadata, and optimize MP4/MOV
containers for playback. These compatibility settings reduce persistent
background artifacts in hardware-accelerated players without changing the
configured CRF, bitrate, preset, or pixel format.

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

In Project Studio, `Bar appearance > Content` exposes the primary
logo size through `ChartConfig.logo_size`, alongside its position, shape,
padding, background, and border controls. The secondary logo keeps its own
independent size and styling, so changing either logo does not resize the
other.

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
