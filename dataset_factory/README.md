# BarChart Dataset Factory

Independent dataset-curation project for BarChartStudio.

This project does not render videos. Its job is to help build, classify,
validate, and document datasets before they are used by BarChartStudio.

## Dataset Rules

Every production CSV for the channel must have:

- Verifiable real source.
- Clear metric.
- Complete years for the intended story.
- No invented values.
- Source and methodology note.
- BarChartStudio-compatible format.
- Download or access date.

If a clean dataset does not exist, do not invent one. Mark it as:

```text
Type B - Requires extraction
```

## Classification

| Type | Meaning |
|---|---|
| `A` | Ready for production: real data, verifiable source, clean CSV/API path |
| `B` | Requires extraction: source exists, but needs scraping/API/manual cleanup |
| `C` | Not recommended: subjective, unreliable, or not defensible |

## BarChartStudio CSV Format

Default compatible columns:

```csv
year,country,value
2024,Coal,10543
```

The names can be changed per dataset, but each dataset must define:

```text
year_column
name_column
value_column
```

## CLI

From the repository root:

```powershell
.venv\Scripts\python.exe dataset_factory\src\main.py catalog
.venv\Scripts\python.exe dataset_factory\src\main.py inspect data\datasets\global_electricity_sources.csv
.venv\Scripts\python.exe dataset_factory\src\main.py validate data\datasets\global_electricity_sources.csv
.venv\Scripts\python.exe dataset_factory\src\main.py manifest-template fifa_mens_world_ranking
```

## Recommended First Dataset Strategy

Start with datasets that are defensible and already have real source material:

- FIFA men's world ranking points.
- World Bank population.
- World Bank GDP.
- FIFA World Cup results.

Avoid beginning with vague popularity claims unless they are converted into a
verifiable metric. For example:

```text
Most Popular Football Players
```

should become:

```text
Most Searched Football Players on Google
Metric: Google Trends search interest index
```

That is a `Type B` dataset because it requires careful extraction and
normalization.
