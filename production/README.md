# Automated production example

This directory contains a small, synthetic, offline example of the
BarChartStudio production pipeline. It does not download datasets or logos and
is fully self-contained within the tracked production example directories.

From the repository root, run:

```powershell
.venv\Scripts\python.exe src\tools\run_production.py `
  --brief production\briefs\examples\national_team_goals_demo.json `
  --root .
```

The command creates an isolated workspace at:

```text
output/.production_jobs/national-team-goals-demo/
```

The generated project is `project/project.json`, the final video is
`render/video.mp4`, and deterministic stage manifests are stored under
`manifests/`. The example uses no logo directories; add only local paths under
an untracked brief when testing private assets.

The command never overwrites an existing workspace. Remove or archive an old
ignored example workspace deliberately before running the same tracked brief
again.
