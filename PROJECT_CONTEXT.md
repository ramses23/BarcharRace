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
- External project files use `schema_version`; version 1 is current.
  Unversioned/version-0 data is migrated in memory before validation and saved
  back as version 1. The v0 migration moves legacy `chart.animation` and
  `chart.selection` sections to the top level and normalizes legacy logo
  positions. Future versions fail explicitly rather than silently falling back.
- Project-specific source labels through `DataSourceConfig.source_label_override`.
- Project-specific category labels and colors through the top-level
  `categories` section in external project files.
- Project-specific category logos through `categories.<raw_name>.logo`, with
  Project Studio support for uploading a logo folder, choosing individual
  logos, uploading individual logos, or auto-matching files by category name.
- An optional second independent logo is stored in
  `categories.<raw_name>.secondary_logo`. Project Studio can upload, match, and
  place this second slot without changing the primary logo. The renderer
  supports side-by-side, overlay, and badge-style compositions with independent
  position and mask controls.
- A user-provided electricity project exists at
  `projects/global_electricity_sources.json` with data in
  `data/datasets/global_electricity_sources.csv`.
- Top-N bar selection and optional "Other" aggregation.
- Per-year sprite precomputation to avoid repeated selection and layout work
  across transitions.
- Basic per-stage render profiling for larger-dataset tuning, shown in CLI output and Project Studio after video renders.
- Renderer caches logos already resized to `ChartConfig.logo_size` to avoid repeatedly resampling large image assets per frame.
- `BarRenderer` reuses a single Matplotlib figure/axis and a bounded set of bar,
  shadow, and text artists. Frames update artist properties instead of clearing
  the axis and rebuilding every artist; logos use a global sprite compositor.
- Gradient bars are rendered as one reusable `PolyCollection` with a 64-segment
  baseline per visible bar plus localized curve detail, avoiding a separate
  bicubic `AxesImage` resample for every bar on every frame.
- Advanced materials are assembled by a reusable custom Agg artist. The
  renderer caches each 256x64 category material, resized fills, antialiased
  shape masks, border masks, and logo sprites with bounded LRU stores. For every
  frame it composites fill, texture, depth, shine, and border into compact
  per-bar RGBA sprites and submits them directly to Agg. Track, projected
  shadow, and glow are batched into three global vector collections to preserve
  correct underlay ordering during rank crossings. Text remains a separate sharp
  layer. Logos are clipped, backed, bordered, and faded inside cached compact
  sprites submitted by one global direct Agg artist. This path supports every
  Advanced shape/effect combination without falling back to the old
  clipped-image stack.
- In an identical repeated eight-bar 1080p A/B check, the compositor reduced
  Advanced Fill from 0.1367s/frame to 0.0983s/frame and the fully layered sample
  from 0.1570s/frame to 0.1296s/frame. On the real 457-frame cumulative
  national-team project with inside-right flags, total time fell from 100.213s
  to 57.146s, while draw time fell from 96.494s to 54.601s.
- Static background images are fitted to the final canvas once and submitted
  through a reusable direct Agg artist instead of a full-canvas `AxesImage` on
  every frame. The 457-frame Advanced project with 316 matched logos and a JPEG
  background fell from 206.162s total / 202.250s draw to 67.430s total /
  64.714s draw, preserving `cover`, `contain`, and `stretch` behavior.
- The general logo compositor replaces each visible logo's Matplotlib image and
  three supporting patches in both Simple and Advanced modes. It preserves all
  positions, adaptive/explicit shapes, opacity, background, and border controls.
  On that same 457-frame project it reduced 67.430s total / 64.714s draw again
  to 57.022s total / 54.297s draw.
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
- Project Studio builds an immutable `ProjectDraft` snapshot from the form and
  tracks a canonical fingerprint of both its JSON data and destination path.
  `Save project` is explicit, saved/unsaved status is visible, and preview/video
  actions save that exact snapshot before invoking the shared render pipeline.
- The latest preview path and its draft fingerprint live in session state. The
  preview therefore survives normal widget reruns and is visibly marked stale
  after the user changes the draft.
- The selected CSV is read through a bounded `st.cache_data` loader keyed by
  resolved path, file size, and nanosecond modification time. Dataset preview,
  inspection, periods, and categories share the cached DataFrame, while a file
  replacement at the same path invalidates it.
- The category editor searches and filters the full dataset, but mounts only a
  page of 10, 20, or 40 editable rows. Page fields live in a Streamlit form, so
  typing does not rerun the entire application. `Apply category changes`
  commits that page to a session-backed category draft, which persists across
  filters/pages and participates in the next project draft. Bulk primary and
  secondary logo matching still covers every category.
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
- Font selection, visual text placement, and bar appearance are Custom
  Components v2. Inline source assets are registered once per active Streamlit
  component manager, state is synchronized through named `setStateValue`
  fields, and styles are isolated with Streamlit theme CSS variables. Do not
  reintroduce `components.v1`, iframe messages, or manual frame sizing.
- Bar-appearance fields are contextual. Simple and Advanced mode, fill type,
  texture, bevel, glow, shine, track, primary/secondary logo, border,
  background, and value styling controls reveal only their active dependents.
  Hidden values remain in normalized settings for reversible switching.
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
- Final video rendering is preceded by a structured preflight covering project
  parsing, data loading/validation, minimum period count, FFmpeg, output path,
  required background/texture assets, and optional logo warnings. Errors block
  launch.
- Final renders run in an isolated worker process controlled by
  `src/ui/render_controller.py`. Progress is throttled into an atomic status
  file under `output/.render_jobs/<job_id>/`; stdout/stderr go to that job's
  log. The Streamlit UI polls only an active fragment and can terminate the
  worker plus its FFmpeg child tree.
- The worker renders to a job-specific partial MP4 and atomically replaces the
  configured output only after success. Failure/cancellation removes the
  partial file and preserves the previous completed video.
- Project JSON saves are atomic temporary-file replacements through
  `src/studio/project_storage.py`. In-app project/new-CSV switching requires
  confirmation when the draft fingerprint differs from the saved fingerprint;
  `Keep editing` restores the complete captured draft.
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

The latest technical direction is to make local development and verification
reproducible now that the editor/render workflow has stable modular boundaries.

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
- `src/renderer/artists.py` owns the reusable Matplotlib image artist
  primitives. `src/renderer/text_compositor.py` owns rasterized text, font
  lookup, and text sprite caches. `BarRenderer` coordinates those pieces and
  the bar appearance/layout paths.
- `VideoExporter` exports PNG sequences or opens a raw RGBA FFmpeg stream.
- `ChartConfig.frame_output_mode` selects `png_sequence` or `ffmpeg_stream`.
- Project Studio's form may create a `ProjectDraft`, but only
  `save_project_data` persists it. The UI must not treat incidental widget
  reruns as saves.
- Custom UI wrappers own CCv2 registration/state hydration. Renderer and config
  modules must never depend on Streamlit component result objects.
- UI dataset caching belongs in `src/ui/dataset_cache.py`. Data importers and
  the render pipeline remain independent of Streamlit.
- Render preflight/progress/cancel/status/profile presentation belongs in
  `src/ui/render_workflow.py`, not in the project form or pipeline.
- `src/studio/render_worker.py` may construct and run `RenderJob`, but it must
  not duplicate pipeline stages. Its responsibilities are process isolation,
  status transport, and atomic promotion of successful video output.
- A UI cancel action must terminate the whole render process tree so an FFmpeg
  child cannot remain orphaned.
- Pixel-exact Simple and Advanced frame signatures are renderer contracts. An
  intentional visual change must be inspected before updating their expected
  hashes.

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
- Project schema ownership lives in `src/config/project_schema.py`. Every new
  schema version adds one sequential migration from the immediately preceding
  version; migrations deep-copy their input and never mutate caller data.
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
- Increment `CURRENT_PROJECT_SCHEMA_VERSION` only for a persisted contract
  change, and add a deterministic migration from the previous version.
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

The current consolidation program precedes additional chart types. Complete it
in verified, published checkpoints:

1. **Draft and rerun foundation — completed.** Use immutable draft snapshots,
   explicit save/dirty status, persistent previews, and one bounded cached CSV
   load shared by the editor.
2. **Scalable category editor — completed.** Search/filter the entire category
   set, mount only a configurable page, preserve applied pages in the session
   draft, and use a deliberate form submit to avoid rerunning on every field
   edit.
3. **Reliable rendering workflow — completed.** Preflight validation,
   cancellable isolated rendering, atomic JSON/video promotion, persistent job
   logs/status, and confirmation for destructive in-app draft transitions are
   implemented. Browser/tab close cannot be intercepted reliably; the visible
   dirty indicator remains the close warning.
4. **Versioned configuration — completed.** Schema version 1, sequential
   migration infrastructure, legacy normalization, future-version rejection,
   versioned builder/storage output, and a canonical sample are implemented.
5. **Modern components — completed.** Font, layout, and bar controls use CCv2
   with isolated themed styles and controlled named state. Legacy iframe APIs
   are removed, and dependent Advanced controls are generated contextually.
6. **Modular renderer and UI — completed.** Reusable image artists, the cached
   text compositor, and render-workflow presentation have dedicated modules.
   Pixel-exact Simple and Advanced frame signatures guard renderer output.
7. **Reproducible development.** Provide a reliable launcher and doctor command,
   pin and document dependencies, add CI checks, and resolve the repository's
   unrelated `main`/`master` history without risking active work.
8. **Portable delivery.** Export/import complete project bundles, surface the
   finished video cleanly in the UI, finish documentation, and run an integral
   end-to-end verification.

Do not collapse these into one large unverified rewrite. Each phase updates
tests, README, and this context file, then is committed and pushed to the active
GitHub branch.

## Non-Goals For Now

- Do not migrate away from Matplotlib until the current engine behavior is
  stable.
- Do not let the GUI duplicate engine pipeline logic; it should drive JSON
  project files and `RenderJob`.
- Do not replace the custom engine with a high-level chart-race package.
- Do not mix business data models with visual state models.
- Do not prioritize additional visual polish for aggregated `Other` bars unless
  the user asks for it explicitly.
