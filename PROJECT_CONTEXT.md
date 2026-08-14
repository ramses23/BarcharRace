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
- Real-glyph text fitting for long labels and value labels using the same
  effective Pillow font, fallback family, size, weight, and DPI as rendering.
- Ellipsis-aware binary-search truncation keeps complete names whenever they
  fit and measures `...` before selecting the longest valid prefix.
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
- Base text opacity is configurable from `0.0` to `1.0` for title, subtitle,
  date, source, category, value, ranking, and Fun Fact headline/body/credit.
  Every field defaults to `1.0` except the historical date watermark at `0.22`.
  The compositor multiplies this base by row animation or Fun Fact fade alpha;
  preview, renderer, Studio, project JSON, Text Placement, and presets share the
  same values.
- Reusable typography presets.
- Four configurable bar shapes: rectangle, rounded, capsule, and lollipop.
- Configurable bar borders, shadows, and gradients, exposed through a live
  appearance editor in Project Studio.
- Bar appearance is edited through one unified, contextual control model with
  an active-settings summary. The renderer automatically keeps compatible
  category-color solids and classic gradients on the vector backend, while
  multi-direction/two-or-three-color materials, custom colors, textures,
  bevel, inner shadow/glow, top/bottom depth, outer glow, shine, and row tracks
  select the cached material backend. Legacy `simple` and `advanced` project
  values remain loadable and pixel-compatible but are not user-facing modes.
  Logos can be outside-left, inside-left, inside-right, or hidden, with adaptive,
  circular, rounded, or square masks plus independent size, padding, background,
  and border controls for the primary and secondary slots. Project Studio
  exposes the primary size through the existing `ChartConfig.logo_size`, which
  preserves compatibility with older project files. Lollipop inside-left logos
  add a circular start socket; inside-right logos occupy the endpoint circle.
  Legacy `outside`/`inside` values are still accepted. Category label alignment
  is independent from its position and can be automatic, left, centered, or
  right within the allocated label area.
- Projected shadow remains a separate layer from bevel, inner shadow, and glow.
- Value format presets.
- Logo resolution and rendering.
- External JSON project files.
- Fun Fact Overlay System V1 schedules one editorial card by exact annual or
  display-only monthly timeline labels. It supports cached
  headline/body/image/credit composition, EXIF-aware cover/contain images,
  alpha fades during existing frames, scheduled and forced previews, Project
  Studio controls, preflight, and portable bundle assets. `right_panel` and
  `editorial_right` reserve a stable full-height column. Editorial Layout V2
  adds a movable `editorial_floating` rectangle with vertical/horizontal
  composition, left/right image placement, and per-row collision geometry.
  Studio also exposes a CCv2 editor with body drag, eight resize handles,
  keyboard movement, canvas bounds, and synchronized X/Y/width/height inputs.
  Card/solid backgrounds can add deterministic grain, paper, dots, or diagonal
  texture at configurable intensity without replacing the base color;
  transparent cards ignore texture.
  None of the layouts changes frame count or FPS.
- External project files use `schema_version`; version 2 is current.
  Unversioned/version-0 and version-1 data are migrated in memory before
  validation and saved back as version 2. The v0 migration moves legacy `chart.animation` and
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
- Renderer caches primary and secondary logos at their configured sizes to
  avoid repeatedly resampling large image assets per frame.
- `BarRenderer` reuses a single Matplotlib figure/axis and a bounded set of bar,
  shadow, and text artists. Frames update artist properties instead of clearing
  the axis and rebuilding every artist; logos use a global sprite compositor.
- Gradient bars are rendered as one reusable `PolyCollection` with a 64-segment
  baseline per visible bar plus localized curve detail, avoiding a separate
  bicubic `AxesImage` resample for every bar on every frame.
- Material styles are assembled by a reusable custom Agg artist. The
  renderer caches each 256x64 category material, resized fills, antialiased
  shape masks, border masks, and logo sprites with bounded LRU stores. For every
  frame it composites fill, texture, depth, shine, and border into compact
  per-bar RGBA sprites and submits them directly to Agg. Track, projected
  shadow, and glow are batched into three global vector collections to preserve
  correct underlay ordering during rank crossings. Text remains a separate sharp
  layer. Logos are clipped, backed, bordered, and faded inside cached compact
  sprites submitted by one global direct Agg artist. This path supports every
  layered shape/effect combination without falling back to the old
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
  three supporting patches in both internal render paths. It preserves all
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
- Workspace Separation V1 distinguishes `APP_ROOT`, `WORKSPACE_ROOT`, and each
  production or scratch `project_root`. Project Studio creates user content in
  the configured external workspace, opens production/scratch projects in
  place, and labels repository examples/projects as read-only sources that are
  cloned to scratch on save. Project fields not exposed in the form remain
  preserved.
- Project Library option identities remain portable paths, while their visible
  labels are deterministic and name-first. Duplicate stems add location
  context; the sidebar displays the full selected name, kind, and portable path.
- Project Studio builds an immutable `ProjectDraft` snapshot from the form and
  tracks a canonical fingerprint of both its JSON data and destination path.
  It also tracks a render-dependency fingerprint and a narrower automatic
  visual fingerprint. `Save project` is explicit, saved/unsaved status is
  visible, and manual preview/video actions save that exact snapshot before
  invoking the shared render pipeline.
- `Auto preview` is enabled by default and watches Canvas, Bars, Fun facts, applied
  category styles, and preview-frame selection. It renders the current
  `ProjectDraft.project_data` through the shared preview pipeline without
  writing the project JSON. Data and Export changes remain manual. Disabling
  the toggle pauses work; enabling it renders one pending visual change.
- Project Studio has a collapsed `Appearance presets` library for reusing the
  combined Canvas, Bars, and Fun Facts appearance across projects. Presets are independent
  versioned JSON files under `presets/appearance/`; save-new, apply, update,
  and confirmed-delete actions operate on that library. Applying changes only
  `CURRENT_DRAFT_STATE`, refreshes visual widgets, and participates in Auto
  preview without saving the destination project JSON.
- The `appearance-preset-v5` contract includes Canvas layout/background,
  typography, text visibility/placement, value formatting, all fields in
  `BAR_STYLE_FIELDS`, and reusable Fun Fact layout/panel/fade/editorial styling,
  including floating-card geometry, all base text opacities, editorial text
  colors, and card texture. V1–V4 remain loadable; missing date opacity receives
  `0.22`, other missing opacities receive `1.0`, and texture defaults to `none`.
  Presets deliberately exclude title/source content,
  Fun Fact enabled/source/content, datasets, selection/Top N, categories and
  their assets, animation, render/export settings, and output paths. Personal
  preset JSON files are Git-ignored; the tracked `.gitkeep` preserves the
  library directory.
- The latest preview path and its canonical, render, and visual fingerprints
  live in session state. The preview therefore survives normal widget reruns
  and is marked stale only when a render-relevant change remains outside the
  automatic visual scope.
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
- Project Studio uses a dark creative-workspace theme defined only through
  `.streamlit/config.toml`: graphite surfaces, violet accent, native borders,
  Inter/JetBrains Mono typography, 512 MB upload/message limits, and a minimal
  toolbar. Do not replace the theme with injected CSS. Viewport anchoring for
  Latest preview is handled by an invisible CCv2 controller rather than global
  theme or layout CSS.
- The workspace is a responsive editor/stage split. A segmented navigator for
  `Data`, `Canvas`, `Bars`, `Fun facts`, and `Export` lives on the left and conditionally
  mounts exactly one section; never replace it with static `st.tabs`, because
  static tabs mount every panel and can expose all sections after component
  reruns. Hidden-section values are reconstructed from `CURRENT_DRAFT_STATE`,
  while preview-only controls use `PREVIEW_SETTINGS_STATE`, so section changes
  preserve unsaved settings. Project actions, persistent preview, render
  state/video, dataset snapshot, portable bundle, and generated JSON live on
  the right. A compact out-of-order header shows project identity, dataset
  dimensions, destination JSON, and dirty/saved state.
- Controls retain that navigator and their existing widget keys, but are
  grouped by identity/mapping/source, canvas/content/typography,
  selection/appearance, Fun Fact scheduling/editorial geometry, and
  motion/encoding/output. CPU preferences are visually separated inside the
  Workspace panel and appearance presets remain collapsed.
- Project/CSV loading and bundle import remain in the sidebar project library.
  Unsaved destructive transitions use a non-dismissible `st.dialog`. Advanced
  controls use icon-labelled collapsed expanders to reduce initial density.
  The redundant `Theme` and `Typography` selectors are hidden, but their
  stored values remain compatible with older project files.
- For new projects, Project Studio derives the title, project name, project JSON
  path, output MP4 path, and frames directory from the selected CSV filename.
- Project Studio can render selected-year previews and transition-point
  previews before generating the full video.
- Project Studio exposes font-family selectors for title, subtitle, category
  labels, values, date, source, and ranking. The selectors use a curated list
  of up to 30 common installed fonts and render each option in its own family.
  Each element falls back to the active theme font when its family is null.
- Font selection, visual text placement, editorial-card geometry, and bar appearance are Custom
  Components v2. Inline source assets are registered once per active Streamlit
  component manager, state is synchronized through named `setStateValue`
  fields, and styles are isolated with Streamlit theme CSS variables. Do not
  reintroduce `components.v1`, iframe messages, or manual frame sizing.
- Editorial-card gestures remain local in JavaScript and emit only at the end.
  Each event includes an instance-scoped id and its starting rectangle; Python
  consumes it once and accepts it only if the draft still matches that base.
  This replaces monotonic frontend revision comparisons, which were unsafe
  across CCv2 remounts, and prevents stale gestures from overwriting numeric or
  section changes. External reruns do not rebuild the DOM during pointer capture.
- Bar-appearance fields are contextual. Fill type, texture, bevel, glow, shine,
  track, primary/secondary logo, border,
  background, and value styling controls reveal only their active dependents.
  The CCv2 frontend stores each control group's expanded state per mounted
  component and captures it before rebuilding the DOM, so field updates do not
  collapse the section being edited. New bar-style changes persist the
  `unified` model; legacy mode values are converted for editing without
  rewriting an untouched project.
- Project Studio exposes point-size controls for title, subtitle, category,
  value, date, source, and ranking text. A visual layout editor lets users drag
  title, subtitle, date, and source on a scaled canvas, nudge with arrow keys,
  align horizontally, and reset to preset positions. Text Placement V2 gets a
  real selected frame from Python and draws `SceneGeometry` overlays for data,
  rows, actual bar extents, text bounds, ranking/category/value lanes, logo
  slots, editorial card, and collision area. JavaScript only scales this
  geometry; it must not duplicate `LayoutEngine`. X/Y coordinates remain the
  persisted format. Unset title/subtitle X coordinates inherit
  `ChartConfig.left_margin` for backward compatibility.
- Project Studio exposes `Category label start`, `Bar start`, and `Category
  area span` in Canvas. They persist `label_min_x`, `left_margin`, and
  `rank_label_gap`; older projects inherit layout-preset defaults. `Use full
  left space` derives the span needed to preserve `rank_label_min_x` while
  giving names the unused horizontal area before the bars.
- Project Studio exposes independent text colors for title, subtitle, category,
  value, date, source, and ranking. The optional `*_text_color` fields inherit
  the legacy theme colors when absent, preserving older project rendering.
- Project Studio exposes independent visibility toggles for title, subtitle,
  date, source, ranking, category, and value text. The persisted
  `*_enabled`/`*_labels_enabled` fields default to true for older projects,
  participate in automatic-preview fingerprints, and suppress the same layers
  in preview and final-video rendering without discarding their styles.
- `AnimationConfig.motion_mode` supports `transition_easing` (legacy default)
  and `continuous`. Continuous mode uses bounded Catmull-Rom interpolation with
  neighboring annual keyframes, keeps velocity continuous for persistent bars,
  preserves eased fades for entries/exits, and emits year-boundary frames once.
- Project Studio shows render progress while launching a final video render.
- Final video rendering is preceded by a structured preflight covering project
  parsing, data loading/validation, minimum period count, fun fact schedules,
  FFmpeg, output path, required background/texture/fun-fact assets, and optional logo warnings. Errors block
  launch.
- Final renders run in an isolated worker process controlled by
  `src/ui/render_controller.py`. Progress is throttled into an atomic status
  file under `WORKSPACE_ROOT/cache/render_jobs/<job_id>/`; stdout/stderr go to
  that job's log. The Streamlit UI polls only an active fragment and can terminate the
  worker plus its FFmpeg child tree. Atomic JSON replacement retries transient
  destination locks with bounded backoff, which is required on Windows while
  Streamlit, antivirus, or indexing software reads `status.json`. A progress
  status write is non-fatal telemetry: after retries are exhausted it is logged
  and skipped, so status-file contention cannot abort the actual render.
- The worker renders to a job-specific partial MP4 and atomically replaces the
  configured output only after success. Failure/cancellation removes the
  partial file and preserves the previous completed video.
- A completed render remains in the status card with an embedded player, file
  path/size, profile, and MP4 download. Files over 200 MB are played from disk
  but are not copied into Streamlit's in-memory download buffer.
- `src/studio/project_bundle.py` exports a bundle-schema-v1 `.barchart.zip`
  containing versioned project JSON, CSV/SQLite data, background, custom
  texture, both logo slots, fun fact JSON, and local fact images. Its manifest records SHA-256 and size per file.
  Import validates paths, membership, checksums, compression, symlinks,
  encryption, size/file-count limits, then stages assets before atomic project
  creation. Collisions receive `_2`, `_3`, etc.; existing projects are never
  overwritten.
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
- Text fitting resolves the same effective font file used by the renderer,
  converts point size through the configured DPI, measures real glyph bounds
  with Pillow, and includes the ellipsis width before truncating.
- The large time label is rendered as a background watermark behind bars and
  source text.
- MP4 export with configurable FFmpeg codec, CRF, bitrate, preset, and pixel
  format.
- `libx264` export uses a closed two-second GOP, one reference frame, no
  B-frames, limited-range BT.709 VUI metadata, and fast-start MP4/MOV metadata
  to reduce persistent background shadows caused by corrupted temporal
  references in hardware-accelerated players. Other codecs keep their existing
  command.
- Unit tests and a real FFmpeg integration test.
- The automation workstream begins with a renderer-independent dataset layer in
  `src/automation`. `DatasetBuilder` is the common structural contract and
  `DatasetBuildResult` records immutable provenance, hashes, sizes, effective
  parameters, warnings, and row statistics without retaining a DataFrame.
- `NationalTeamGoalsDatasetBuilder` currently accepts only a local source CSV
  plus an optional expected SHA-256. It builds deterministic annual or
  cumulative `year,country,value` output, validates full match dates and
  non-negative integer scores, explicitly rejects boolean scores, and never
  overwrites an output. Publication currently uses a same-directory hardlink;
  after the link succeeds, temporary-name cleanup is best effort and a residual
  path is reported as a warning without invalidating the completed build.
  Duplicate identity uses every available standard match field; `error` stops,
  `warn` retains and reports, and `allow` retains silently.
- The automated-production MVP is complete in `src/automation` and is exposed
  by the thin `src/tools/run_production.py` command. One validated version-2
  brief now composes dataset construction, optional local logo resolution,
  project assembly, production preflight, and optional isolated rendering.
  The flow reuses the current controller, worker, `RenderJob`, renderer, and
  exporter; it does not create a second rendering pipeline. Dataset building
  and logo resolution perform no network access, downloads, or remote caching.
- `ProductionWorkspace` reserves one exclusive job directory under the
  explicit automation job root (the CLI uses
  `PRODUCTION_ROOT/generated/production_jobs/<job_id>/`), creates
  canonical artifact directories, and writes deterministic version-1 workspace
  manifest and production-status JSON files. Workspace, production-status, and
  project JSON schemas are independent. Failed initialization rolls back only
  the job directory created by that attempt.
- The workspace remains path infrastructure: it exposes canonical
  `logos/primary`, `logos/secondary`, and
  `manifests/logo_resolution.json` paths plus canonical project, video, and
  project-assembly/preflight/render-manifest paths, but it does not execute
  dataset builders, logo resolution, project assembly, preflight, or renders.
- `ProductionBrief` and `DatasetBrief` preserve the exact immutable version-1
  dataset-only contract. `ProductionBriefV2` extends that intent with required
  assets, project, and render sections without silently migrating version 1.
  The strict loader rejects unknown versions, unknown or duplicate fields,
  resolves every source/template/logo path beneath an explicit `root_dir`, and
  stores generic scalar parameters in deterministic, deeply immutable form.
  Loading a brief reads no source content and executes no workspace, builder,
  project, or render work.
- `DatasetBuilderRegistry` is an explicit, immutable mapping from validated
  builder IDs to zero-argument factories and optional parameter parsers. Its
  default registry contains only `national_team_goals`; there is no
  autodiscovery, plugin loading, or mutable global registry. Every builder
  resolution invokes the registered factory and returns a newly validated
  instance. Parameter parsing invokes only the selected parser and never
  creates or executes a builder.
- `NationalTeamGoalsBuildParameters` is the frozen, typed representation of the
  four canonical brief parameters: `start_year`, `end_year`, `mode`, and
  `duplicate_policy`. Its parser is a pure transformation from
  `FrozenParameters`: it accepts no missing or unknown keys, performs no I/O,
  and returns new builder-argument dictionaries on demand. The builder retains
  its independent defensive validation for direct calls; the parser does not
  replace it.
- Registry construction, builder resolution, and parameter parsing do not read
  or write files, create workspaces, or invoke `build()`.
- `ProductionOrchestrator.prepare_dataset()` remains the compatible
  dataset-only entry point for a validated version-1 or version-2 brief. It
  validates containment and registry operations before creating one workspace,
  invokes the builder once, validates the CSV through the existing
  `DatasetValidator`, publishes deterministic `manifests/dataset_build.json`,
  and finishes at `dataset_ready` without duplicating transformation rules.
- `ProductionOrchestrator.run_production()` accepts only a validated version-2
  brief and composes every reusable stage exactly once. Normal state order is
  `dataset_running`, `dataset_ready`, `assets_ready`, `project_ready`,
  `preflight_ready`, `rendering`, and `completed`; the workspace's initial
  state is `created`. Render-disabled jobs stop at `preflight_ready`, and
  `blocked`, `canceled`, and `failed` remain explicit terminal results.
  General status artifacts are available, relative paths only.
- Dataset-stage failures after workspace creation are recorded by best effort
  as `failed` with a non-sensitive phase and exception type. The workspace,
  generated CSV, and any exclusively published manifest are retained for
  audit; failures before workspace creation leave no job directory.
- `LocalLogoResolver` remains a reusable post-dataset component and is invoked
  by the complete orchestrator only when either local logo directory is set.
  It reads only the selected category column, reuses Project Studio's existing
  `match_category_logos()` selection and normalization, resolves optional local
  primary and secondary directories nonrecursively, and copies only selected
  assets into the workspace. Safe deterministic names, SHA-256 values, sizes,
  missing categories, detectable ambiguities, and warnings are recorded in the
  independent deterministic `manifests/logo_resolution.json` schema.
- Local logo resolution never downloads assets, calls the network, applies
  category styles, creates a BarChartStudio project, or changes `status.json`.
  A workspace at `dataset_ready` therefore remains at `dataset_ready`. A prior
  logo-resolution manifest or nonempty primary/secondary target directory is
  rejected instead of overwritten; publication failure rolls back only assets
  and slot directories created by that attempt.
- `ProductionProjectAssembler` remains the reusable project stage. It validates
  a `DatasetProductionResult` and optional
  `LogoResolutionResult`, loads and migrates a visual template through the
  existing project APIs, filters obsolete category styles, applies both logo
  slots through `apply_category_logo_matches()`, and delegates schema creation
  and storage to `build_project_data()` and `save_project_data()`. The finished
  `project/project.json` is reloaded through `load_project_file()` before the
  independent deterministic `manifests/project_assembly.json` is published.
- Assembled dataset, logo, project, template, frames, and MP4 references are
  portable POSIX paths relative to an explicit project root. The result records
  immutable project provenance, hashes, sizes, category/logo counts, output,
  and warnings. Project assembly reserves its destination exclusively and
  never creates the configured `render/video.mp4`. The component does not write
  general production status; the complete orchestrator publishes
  `project_ready`. A later-stage failure rolls back only the project created by
  that attempt.
- `ProductionPreflightRunner` remains the reusable readiness stage after
  project assembly. It verifies assembly provenance and referenced
  dataset/logo files, reloads the project, and delegates render readiness to the
  existing `run_render_preflight()` exactly once. Blocking checks produce an
  immutable `blocked` result instead of an exception; warnings do not block, and
  technical validation, execution, adaptation, or publication failures remain
  distinct exceptions with their original causes.
- Production preflight publishes the independent deterministic
  `manifests/production_preflight.json` schema with portable project/output
  references, project hash, FFmpeg availability, sanitized errors and warnings,
  and `ready` or `blocked` status. It does not modify `status.json`, correct
  configuration, create frames or MP4 output, execute FFmpeg, or start a render.
  The component does not write general status; the complete orchestrator
  publishes `preflight_ready` or `blocked`.
- `ProductionRenderExecutor` remains the reusable, blocking render stage after
  a `ready` production preflight. It revalidates workspace identity, assembly and
  preflight manifests, project hash/size, project loading, configured output,
  and exclusive destination/partial-file state before launching anything. It
  then reuses `start_background_render()`, `BackgroundRender.status()` and
  `BackgroundRender.cancel()`, and `render_result_from_status()`; it never
  creates a second rendering pipeline or invokes `RenderJob` or FFmpeg directly.
- A completed render produces canonical `render/video.mp4` plus the independent
  deterministic `manifests/production_render.json` schema. The immutable result
  records the final status, MP4 SHA-256 and size, frames, transitions, FPS,
  playback duration, stable `RenderProfile`, and immutable warnings. Worker
  failures preserve their isolated status/log evidence and publish no success
  manifest; manifest-publication failure preserves an already valid MP4.
  Cancellation is represented explicitly through the controller contract and
  cannot promote an incomplete final MP4.
- The render executor deliberately does not modify general production
  `status.json`; `ProductionOrchestrator` owns `rendering` and the final
  `completed` or `canceled` transition around it. Brief, workspace, dataset
  builder, registry, project JSON, worker status, and production status remain
  separate versioned contracts.
- The tracked synthetic example lives under `production/` and runs through
  `.venv\Scripts\python.exe src\tools\run_production.py --brief
  production\briefs\examples\national_team_goals_demo.json --root .`.
  Each job reserves `generated/production_jobs/<job_id>/` without overwrite and
  publishes its dataset, project, optional MP4, manifests, and portable status.
- The MVP remains local and single-job: automatic downloads, remote logo
  discovery, a production queue or scheduler, retry/resume recovery, cloud
  publication, and a new Project Studio automation interface are out of scope.

The eight-phase consolidation roadmap is complete. Future work should start
from a concrete chart type or user workflow and preserve the contracts below.

## Workspace Separation V1 Contract

Filesystem ownership is an architectural boundary, not a `.gitignore`
convention:

- `APP_ROOT` is the Git checkout. Normal use may read source, tracked examples,
  official presets, documentation, and small fixtures there. User projects,
  datasets, uploaded assets, previews, frames, renders, package state, and
  caches must not be written there.
- `WORKSPACE_ROOT` is external user storage. Without a setting it is derived as
  the sibling `<APP_ROOT name>Workspace`; the configured absolute path is stored
  atomically outside Git at `%LOCALAPPDATA%/BarChartStudio/settings.json` on
  Windows. Workspace and settings paths reject unsafe overlap and existing
  symlink/junction components.
- A production `project_root` is
  `WORKSPACE_ROOT/productions/<production_slug>/`. A standalone draft uses
  `WORKSPACE_ROOT/scratch/<project_slug>/`. Relative data, asset, background,
  logo, texture, and fun-fact paths resolve from this root. Output paths resolve
  from an explicit output root and cannot escape it.

The shared V1 workspace directories are only `productions/`, `scratch/`,
`packages/`, and `cache/`. Productions are self-contained and may create
`data/`, `projects/`, `assets/`, `fun_facts/`, `output/`, and `generated/` as
needed. Preview output belongs under `<project_root>/output/previews/`; MP4s
belong under `<project_root>/output/races/` or `output/master/`; temporary
frames belong under `<project_root>/output/frames/`; Studio render status belongs
under `WORKSPACE_ROOT/cache/render_jobs/`.

`src/studio/workspace_paths.py` owns settings, initialization, explicit project
location classification, and the app-root write guard.
`src/studio/package_paths.py` owns portable input containment and link/traversal
rejection. `src/studio/project_runtime.py` resolves a loaded preset against its
separate project and output roots. Callers must pass root meaning explicitly;
do not reintroduce a variable where repository root, workspace root, and
project root are interchangeable.

Project Studio discovers workspace productions, then scratch projects, then
tracked examples and repository legacy projects. Legacy/example locations are
readable but not normal save targets; the first save clones their editable JSON
to scratch and preserves original input references without modifying or
migrating the source files.

Portable bundle import validates and stages under workspace cache, then
atomically installs a complete production under
`WORKSPACE_ROOT/productions/<slug>/`. Production binding schema 2 stores a
portable `production_reference` plus `project_relative_path`; legacy schema 1
bindings remain readable. A package import must never create editable projects,
datasets, or assets under the repository.

Official application presets remain under `APP_ROOT/presets/`. Tracked examples
should evolve toward `APP_ROOT/examples/`; existing `APP_ROOT/projects/*.json`
files are a backward-compatibility source, not a destination.

No automatic migration of existing local repository content belongs in V1. A
future Workspace Migration tool should inventory legacy files, group them by
proposed production, copy before any mutation, verify size and SHA-256 for every
copy, emit a reviewable report, and retain every source until the user approves
a separate deletion phase. It must support dry-run/resume and never infer
destructive permission from workspace initialization.

## Architecture Contract

Keep the pipeline clean:

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
        -> PNG frames -> VideoExporter -> MP4 (png_sequence, optional fallback)
        -> RGBA memory -> FFmpeg stdin -> MP4 (ffmpeg_stream, default)
```

Important boundaries:

- `main.py` must stay thin. It is only the CLI entry point.
- `RenderJob` owns orchestration of the render workflow.
- `RenderJob` may report progress, but UI-specific rendering of that progress
  belongs outside the pipeline.
- Importers load data only. They should not know about rendering.
- Automation dataset builders transform explicit local inputs only. They must
  remain independent from Streamlit, project assembly, logos, and `RenderJob`.
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
- `SoftCpuLimiter` cooperatively samples total CPU between frames with
  hysteresis; `VideoExporter` receives its derived FFmpeg thread count. CPU
  policy is an application preference and must never enter project JSON.
- `ChartConfig.frame_output_mode` selects `png_sequence` or `ffmpeg_stream`.
- Project Studio's form may create a `ProjectDraft`, but only
  `save_project_data` persists it. The UI must not treat incidental widget
  reruns or automatic preview renders as saves. In-memory preview loading may
  build a `ProjectPreset` from draft data, but it must reuse the shared project
  loader validation and rendering pipeline.
- Custom UI wrappers own CCv2 registration/state hydration. Renderer and config
  modules must never depend on Streamlit component result objects.
- `src/core/scene_geometry.py` owns renderer-adjacent overlay geometry in
  final-canvas pixels. `src/studio/layout_preview.py` builds the selected Studio
  scene through Timeline/selection/layout without rendering it. Text Placement
  and the editorial-card editor must share this contract. Their JavaScript may
  scale/draw and handle local gestures, but geometry truth remains in Python.
- UI dataset caching belongs in `src/ui/dataset_cache.py`. Data importers and
  the render pipeline remain independent of Streamlit.
- Render preflight/progress/cancel/status/profile presentation belongs in
  `src/ui/render_workflow.py`, not in the project form or pipeline.
- `src/studio/render_worker.py` may construct and run `RenderJob`, but it must
  not duplicate pipeline stages. Its responsibilities are process isolation,
  best-effort progress status transport, reliable terminal status, and atomic
  promotion of successful video output. Progress reporting failures must never
  propagate into `RenderJob` and stop frame generation.
- A UI cancel action must terminate the whole render process tree so an FFmpeg
  child cannot remain orphaned.
- Pixel-exact legacy Simple and Advanced frame signatures are renderer
  contracts; the unified classic gradient must match the Simple signature. An
  intentional visual change must be inspected before updating expected hashes.
- `scripts/run_studio.ps1` is the canonical Windows entry point. It must invoke
  `.venv\Scripts\python.exe` explicitly and run the environment doctor before
  starting Streamlit.
- `requirements.txt` is the fully pinned environment lock used locally and in
  CI. Dependency changes must update the lock, pass `pip check`, and pass the
  Windows/Python 3.13 workflow.
- Project bundle filesystem and integrity logic belongs in
  `src/studio/project_bundle.py`; the Streamlit layer only initiates it and
  presents results. Bundle schema versioning is independent from project JSON
  schema versioning.
- Bundle import must never call `extractall`, trust archive paths, overwrite an
  existing project, or write files before membership/checksum validation.
- Finished-video playback/download presentation belongs in
  `src/ui/video_output.py`; `RenderJob` remains unaware of Streamlit.

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
optional ActiveFunFact
```

Avoid reintroducing overlapping models such as `BarState`. Visual animation
should work on `BarSprite`.

## Configuration Direction

Prefer configuration over code edits for user-facing video definitions.

Current configuration layers:

- Internal presets live in `src/config/project_preset.py`.
- New external project files live inside a workspace production's `projects/`
  directory or in a scratch project root. Repository `projects/*.json` files
  are legacy/read-only inputs during the transition.
- Timeline-bound editorial overlays use the optional top-level `fun_facts`
  section plus an independent version-1 external JSON file. `Timeline` resolves
  exact display labels from `DatasetConfig.time_label_column`, or `str(period)`
  for older annual projects. V1 rejects overlapping ranges and supports one
  cached overlay without adding frames or changing duration. The
  `editorial_floating` layout does not shrink every row to a fixed column:
  `LayoutEngine` intersects the configured card rectangle with row bands,
  reserves the measured value lane where needed, and applies the strictest
  resulting limit as one common pixels-per-value scale to all bars.
  The generic engine validates, schedules, packages, and renders only supplied
  local content; editorial selection, image discovery/download, licensing, and
  topic-specific facts remain responsibilities of separate production packages.
- Reusable Canvas + Bars + Fun Facts appearance presets live in
  `presets/appearance/*.json` and are owned by
  `src/studio/appearance_presets.py`. Keep their schema independent from the
  project schema, validate them through the normal project loader, and apply
  them only to the destination project's reusable visual fields. V5 includes
  every base text opacity, editorial text colors, and card texture; V4 includes
  date opacity; V3 includes
  floating editorial position, size, orientation, image side, and collision
  gap; V1–V4 remain readable through compatibility defaults.
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
- Uploaded logo folders are copied under the active project root's
  `assets/logos/` or `assets/logos_secondary/`, and that project-relative folder
  becomes the active source for category matching.
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
- Keep generated files out of Git and route them through `WORKSPACE_ROOT`.
  Repository `output/` remains ignored only as a second defense for legacy/dev
  flows; `.gitignore` is not the filesystem ownership mechanism.
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

When changing portable bundle support:

- Keep bundle and project schema versions independent.
- Preserve safe-path, checksum, file-membership, size, and no-overwrite tests.
- Add a migration/reader path before incrementing `BUNDLE_SCHEMA_VERSION`.
- Keep at least one real FFmpeg render test sourced from an imported bundle.

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
.\scripts\run_studio.ps1
```

Environment-only validation:

```powershell
.\scripts\run_studio.ps1 -CheckOnly
.venv\Scripts\python.exe src\tools\doctor.py
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

GitHub and `origin/HEAD` both identify `master` as the default branch. No local
or remote `main` branch exists in the current repository, so there is no
unrelated history left to merge or rewrite. Do not create a replacement
`main` branch unless the repository owner deliberately changes this policy.

Current category-label and automatic-preview work branch:

```text
fix-category-label-truncation
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
   dirty indicator remains the close warning. Atomic status updates retry
   transient Windows file locks, and exhausted progress-write failures are
   isolated from the renderer.
4. **Versioned configuration — completed.** Schema version 1, sequential
   migration infrastructure, legacy normalization, future-version rejection,
   versioned builder/storage output, and a canonical sample are implemented.
5. **Modern components — completed.** Font, layout, and bar controls use CCv2
   with isolated themed styles and controlled named state. Legacy iframe APIs
   are removed, and dependent appearance controls are generated contextually.
6. **Modular renderer and UI — completed.** Reusable image artists, the cached
   text compositor, and render-workflow presentation have dedicated modules.
   Pixel-exact legacy Simple and Advanced frame signatures guard renderer
   output, and unified classic gradients are checked against the Simple
   signature.
7. **Reproducible development — completed.** The PowerShell launcher always
   uses the repository `.venv`; the doctor validates Python, dependencies,
   write access, sample configuration, FFmpeg, and FFprobe. Dependencies are
   fully locked, Windows/Python 3.13 CI runs compile/tests/visual signatures,
   and GitHub plus `origin/HEAD` confirm `master` as the sole default branch.
8. **Portable delivery — completed.** Safe manifest/checksum-based ZIP bundles
   carry project JSON, data, and all supported image assets. Imports are staged
   without overwrites, completed videos have playback/download handoff, docs
   are current, and a real FFmpeg render from an imported bundle is covered.
9. **Studio interface redesign — completed.** A native dark theme, responsive
   editor/stage workspace, compact project header, sidebar project library,
   always-visible action card, focused dirty-draft dialog, Material icons, and
   collapsed advanced controls improve hierarchy without changing project or
   renderer contracts. Segmented section navigation mounts only the active
   editor panel and restores inactive values from the current draft, preventing
   multi-panel exposure during widget/component reruns.

10. **Automated production MVP - completed.** Strict version-2 briefs compose
    the existing local dataset builder, optional two-slot logo resolver,
    project assembler, preflight, controller, isolated worker, and renderer.
    A tracked offline example, thin CLI, deterministic manifests, real-worker
    E2E coverage, and explicit non-overwrite workspaces close the first local
    automation workflow without adding downloads or a new UI.

11. **Measured category labels and automatic visual preview - completed.**
    Category names use effective-font glyph measurement and ellipsis-aware
    fitting instead of average character widths. Canvas exposes the persisted
    label boundary, bar start, and category span with compatible preset
    defaults. Project Studio fingerprints visual dependencies and renders
    unsaved drafts in memory after Canvas, Bars, category, or preview-frame
    changes without turning Streamlit reruns into project saves.

12. **Adaptive title width - completed.** Titles use the full safe horizontal
    space remaining from their configured start position by default, instead
    of inheriting a fixed typography-preset cap that could add an ellipsis while
    visible canvas space remained. Projects may still set `title_max_width` to
    a numeric value when a deliberately narrower title column is required.

13. **Per-layer text visibility - completed.** Canvas provides persistent,
    default-on toggles for title, subtitle, date, source, ranking, category,
    and value text. The cached compositor and compatibility renderer paths omit
    disabled layers consistently, and visual changes refresh the unsaved
    in-memory preview automatically.

14. **Stable bar-editor panels - completed.** The Bar appearance CCv2 component
    preserves each contextual control group's open or closed state across its
    local redraws and Streamlit reruns. Sliders, checkboxes, colors, and
    selectors can therefore update the live preview without collapsing the
    active group.

15. **Sticky latest preview - completed.** The keyed Latest preview card stays
    in view while users scroll through desktop editor controls, making
    automatic visual changes immediately visible. An invisible CCv2 controller
    switches it to viewport-fixed positioning after it reaches an 80 px header
    offset, preserves its original flow space with a placeholder, and tracks
    width/position changes across scroll, resize, and Streamlit reruns. Below
    900 px it restores normal flow so the card does not obstruct stacked mobile
    controls.

16. **Reusable appearance presets - completed.** Project Studio saves the
    current Canvas, Bars, and Fun Facts appearance as strict local
    `appearance-preset-v5` JSON, then applies, updates, or deletes it from a
    shared library. V1–V4 files remain compatible. Applying a preset preserves
    destination data, content, Fun Fact source/enabled state, categories,
    motion, and export settings, remains an unsaved draft change, and refreshes
    the automatic preview.

17. **Fun Fact Overlay System V1 - completed.** Projects can reference a
    strict version-1 fun fact JSON, resolve annual or monthly display labels
    through `Timeline`, reserve a stable right editorial panel, render cached
    text/photos with fades while bars keep moving, force a selected Studio
    preview, validate schedules/assets in preflight, and carry all referenced
    files through portable bundles without changing video duration.

18. **Workspace Separation V1 - completed locally.** Application-owned files
    remain under `APP_ROOT`; new productions, scratch projects, uploads,
    previews, renders, package imports, bindings, and caches route through an
    external configurable `WORKSPACE_ROOT`. Production-relative paths,
    self-contained package installs, explicit write guards, legacy/example
    read compatibility, native Studio workspace controls, and temporary-root
    security tests establish the boundary without migrating any real local
    content.

19. **Editorial layout and render controls V1 - implemented for acceptance.**
    Project Studio adds a backwards-compatible manual/fill-available vertical
    bar layout, five canonical category-label positions with X/Y offsets and
    collision fallbacks, and `editorial_right` fun facts with configurable
    typography, image treatment, background, spacing, and a real timeline date
    at the top of the reserved column. The global settings file adds an
    enabled-by-default 95% soft CPU ceiling, cooperative frame throttling, and
    proportional FFmpeg threads; 100% is unlimited. Five 1920x1080 acceptance
    previews and their JSON inputs are generated only under
    `WORKSPACE_ROOT/scratch/editorial_layout_render_controls_v1_acceptance/`.

20. **Editorial Layout V2 - implemented.** Fun Facts can use an explicit
    `editorial_floating` rectangle instead of reserving the whole right column.
    Project Studio exposes vertical/horizontal composition, X/Y, width/height,
    left/right image placement, and a safety gap. The renderer composes the
    horizontal card natively, while `LayoutEngine` detects which bar rows
    intersect the rectangle and derives one common collision-safe
    pixels-per-value scale. Rows outside the card band retain the available
    canvas width, and bars, inside logos, plus outside/automatic values stay
    clear of the card. Project JSON, auto preview, render jobs, portable
    bundles, and appearance presets all use the same configuration; older
    fixed-column layouts and V1–V4 presets remain compatible.

21. **Editorial card reliability, complete text opacity, and card texture -
    implemented.** The floating-card CCv2 editor reconciles instance-scoped
    gesture events against their starting rectangle instead of comparing a
    frontend revision counter that resets on remount. Drag/resize remains
    local and emits once at gesture end; external reruns preserve pointer
    capture, while duplicate or stale events cannot overwrite the draft.
    Canvas, Bars, and Fun Facts expose all requested base text opacities, which
    multiply animation/fade alpha in preview and render. Editorial backgrounds
    add deterministic grain, paper, dots, or diagonal textures with intensity,
    color preservation, transparent-mode bypass, V5 preset persistence, and
    backward-compatible defaults.

21. **Unified bar appearance - implemented.** Project Studio exposes one Bars
    appearance model instead of mutually exclusive Simple and Advanced modes.
    Contextual groups and active-setting chips make the effective combination
    explicit. The renderer selects the vector or cached material backend from
    the active features, while legacy `simple`/`advanced` JSON remains loadable
    and unchanged until the user edits its bar style. Loader, layout, renderer,
    CCv2 state, documentation, and pixel-exact regressions share this contract.

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
