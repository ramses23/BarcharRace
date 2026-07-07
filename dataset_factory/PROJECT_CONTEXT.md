# Dataset Factory Context

This is an independent companion project for BarChartStudio.

BarChartStudio renders videos. Dataset Factory prepares reliable datasets for
those videos.

## Contract

Dataset Factory should produce CSV files and metadata that BarChartStudio can
use without changing the render engine.

Default output CSV shape:

```text
year,country,value
```

Metadata should explain:

- source name
- source URL
- metric
- unit
- download/access date
- methodology note
- classification (`A`, `B`, or `C`)

## Do Not Invent Data

If data cannot be obtained from a verifiable source, classify the idea as
`Type B - Requires extraction` or `Type C - Not recommended`.

Do not fill missing historical values by guessing.

## Near-Term Dataset Ideas

- `fifa_mens_world_ranking`: Type B until an extraction pipeline/source file is
  added.
- `world_bank_population`: Type A candidate.
- `world_bank_gdp_current_usd`: Type A candidate.
- `google_trends_football_players`: Type B.
- `football_players_career_goals`: Type B.

## Relationship To BarChartStudio

BarChartStudio project JSON files should reference curated CSVs from
`data/datasets/`.

Dataset Factory can validate those CSVs and generate metadata, but it should
not import BarChartStudio renderer code.
