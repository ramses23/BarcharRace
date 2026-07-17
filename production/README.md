# Automated production

This directory contains the tracked, synthetic, offline example for the
BarChartStudio automated-production MVP. It performs no downloads and requires
no private datasets or logos.

## Run the example

From the repository root, run exactly:

```powershell
.venv\Scripts\python.exe src\tools\run_production.py `
  --brief production\briefs\examples\national_team_goals_demo.json `
  --root .
```

The example follows the complete production architecture:

```text
brief v2
  -> dataset builder and validator
  -> optional local logo resolver
  -> project assembler
  -> production preflight
  -> render executor
  -> isolated existing worker
  -> MP4
```

It creates one exclusive workspace at:

```text
output/.production_jobs/national-team-goals-demo/
```

The command never overwrites a workspace. If that directory already exists,
use a local brief under `production/briefs/local/` with a new `job_id`; do not
edit the tracked example merely to rerun it.

## Brief v2 format

`production_brief_schema_version` must be exactly `2`. Unknown or duplicate
fields are rejected. The tracked example illustrates every required section:

```json
{
  "production_brief_schema_version": 2,
  "job_id": "portable-lowercase-job-id",
  "dataset": {
    "builder": "national_team_goals",
    "source_csv": "production/inputs/examples/national_team_goals_source.csv",
    "expected_source_sha256": null,
    "parameters": {
      "start_year": 2000,
      "end_year": 2002,
      "mode": "cumulative",
      "duplicate_policy": "warn"
    }
  },
  "assets": {
    "primary_logo_dir": null,
    "secondary_logo_dir": null,
    "missing_policy": "warn"
  },
  "project": {
    "template": "production/templates/national_team_goals_demo.json",
    "name": "portable-project-name",
    "title": "Video title",
    "source_label": "Source shown in the video"
  },
  "render": {
    "enabled": true
  }
}
```

All paths are local and must resolve below the explicit `--root`. Logo
directories are optional. With `render.enabled` set to `false`, the pipeline
stops after a successful preflight and produces no MP4.

Private briefs and source copies belong in the ignored directories:

```text
production/briefs/local/
production/inputs/local/
```

The example brief, template, and source under their `examples/` directories
remain tracked.

## Results and states

Each workspace contains:

```text
input/source.csv
dataset/dataset.csv
project/project.json
render/video.mp4
manifests/dataset_build.json
manifests/logo_resolution.json       # only when logo directories are used
manifests/project_assembly.json
manifests/production_preflight.json
manifests/production_render.json     # only after render/cancel publication
workspace_manifest.json
status.json
```

Manifest and production-status references are relative and portable. The
normal rendered sequence is:

```text
created
  -> dataset_running
  -> dataset_ready
  -> assets_ready
  -> project_ready
  -> preflight_ready
  -> rendering
  -> completed
```

`preflight_ready` is terminal when rendering is disabled. `blocked`, `canceled`,
and `failed` are explicit terminal outcomes for the corresponding cases.

## Open the generated project

Project Studio discovers JSON files under `projects/`. To inspect the generated
project:

1. Keep the complete production workspace in place.
2. Copy `project/project.json` from the workspace to a unique filename under
   `projects/`.
3. Start Project Studio with `.\scripts\run_studio.ps1`.
4. Select the copied JSON in `Open project` and choose `Load project`.
5. Set a new output path before rendering an edited copy.

The copied JSON still references the workspace dataset and optional logos by
paths relative to the repository root.

## MVP boundary

Automated production is currently a local, one-brief-at-a-time command. It does
not download datasets or logos, search remote services, add a Streamlit
automation screen, schedule or queue jobs, retry/resume interrupted workspaces,
or publish results to remote storage. It deliberately reuses the current
BarChartStudio project schema, preflight, worker, renderer, and exporter.
