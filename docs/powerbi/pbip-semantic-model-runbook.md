# PBIP Semantic Model Runbook

## Purpose

Document the local Power BI Project prototype for the LiChess Analytics report.

The current PBIP is a thick project with a report and semantic model stored in source control. The semantic model connects directly to Gold Parquet outputs so the first Power BI prototype stays portable across local development, Fabric Lakehouse, and Databricks-style lake storage.

## Project Location

```text
powerbi/reports/LiChess Analysis/LiChess Analysis.pbip
```

## Data Source Strategy

The first PBIP prototype uses Gold Parquet instead of DuckDB ODBC.

Reasons:

- DuckDB ODBC was not installed on the local machine during inspection.
- Parquet is the project system of record for curated Gold outputs.
- The Parquet pattern maps cleanly to Fabric Lakehouse/Direct Lake and Databricks later.

Fact import path:

```text
data/gold/game/source_month=YYYY-MM/fact_game.parquet
```

Dimension import path:

```text
data/gold/dimensions/*.parquet
```

The `fact_game` Power Query partition uses `Folder.Files` against `data/gold/game`, filters for `fact_game.parquet`, reads each file with `Parquet.Document`, and combines the monthly partitions.

## Model Tables

| Table | Grain | Source |
|---|---|---|
| `fact_game` | One row per game | `data/gold/game/source_month=*/fact_game.parquet` |
| `dim_date` | One row per calendar date | `data/gold/dimensions/dim_date.parquet` |
| `dim_white_rating` | One row per white rating key | `data/gold/dimensions/dim_white_rating.parquet` |
| `dim_black_rating` | One row per black rating key | `data/gold/dimensions/dim_black_rating.parquet` |
| `dim_time_control` | One row per time-control key | `data/gold/dimensions/dim_time_control.parquet` |
| `dim_termination` | One row per termination key | `data/gold/dimensions/dim_termination.parquet` |
| `dim_rating_difference_bucket` | One row per rating-difference bucket key | `data/gold/dimensions/dim_rating_difference_bucket.parquet` |
| `dim_eco` | One row per ECO code | `data/gold/dimensions/dim_eco.parquet` |
| `dim_opening_variation` | One row per observed Lichess opening variation | `data/gold/dimensions/dim_opening_variation.parquet` |

## Relationships

| From | To |
|---|---|
| `fact_game.Date_SK` | `dim_date.Date_SK` |
| `fact_game.WhiteRating_SK` | `dim_white_rating.WhiteRating_SK` |
| `fact_game.BlackRating_SK` | `dim_black_rating.BlackRating_SK` |
| `fact_game.RatingDifferenceBucket_SK` | `dim_rating_difference_bucket.RatingDifferenceBucket_SK` |
| `fact_game.TimeControl_SK` | `dim_time_control.TimeControl_SK` |
| `fact_game.Termination_SK` | `dim_termination.Termination_SK` |
| `fact_game.ECO_SK` | `dim_eco.ECO_SK` |
| `fact_game.OpeningVariation_SK` | `dim_opening_variation.OpeningVariation_SK` |
| `dim_opening_variation.ECO_SK` | `dim_eco.ECO_SK` |

## Starter Measures

Measures currently live on `fact_game`.

| Measure | Definition Intent |
|---|---|
| `Game Count` | Count rows in `fact_game` |
| `White Score %` | Sum white score divided by game count |
| `Black Score %` | Sum black score divided by game count |
| `White Win Rate` | White wins divided by game count |
| `Black Win Rate` | Black wins divided by game count |
| `Draw Rate` | Draws divided by game count |
| `Time Forfeit Count` | Games where termination indicates a time forfeit |
| `Time Forfeit Rate` | Time forfeits divided by game count |

## Git Hygiene

The repo-level `.gitignore` excludes Power BI cache and local settings:

```text
**/.pbi/cache.abf
**/.pbi/localSettings.json
```

Do not commit Power BI cache files. The semantic model metadata, report metadata, theme resource, and `.platform` files are expected source-controlled PBIP artifacts.

## Validation

Preferred validation/tooling order:

1. Use the Power BI MCP server or Power BI Desktop connection tooling when the model is open and runtime validation is needed.
2. Use `pbir-cli` for report/PBIR validation and scripted report edits when available.
3. Use semantic-model, PBIP, and TMDL skills before hand-editing model files.
4. Use report design, visual review, PBIR format, Deneb, SVG, Python/R visual, and theme skills before designing or editing report pages.
5. Direct TMDL edits are acceptable for this prototype, but should be followed by Desktop refresh validation.

Completed checks:

- PBIP structure validator passed with zero errors and zero warnings.
- Report `definition.pbir` resolves to the sibling semantic model by path.
- Repo-level `.gitignore` excludes `.pbi/cache.abf` and `.pbi/localSettings.json`.

Remaining checks:

- Open the PBIP in Power BI Desktop.
- Refresh the semantic model.
- Confirm imported row count matches the DuckDB/Gold validation count for processed months.
- Confirm relationships activate as expected in Model view.
- Add first visual smoke test using `Game Count`, score %, time control, ECO, and rating bands.

## Open The Prototype

Open this file in Power BI Desktop:

```text
C:\Users\marti\OneDrive\Documents\New project\chess-analytics\powerbi\reports\LiChess Analysis\LiChess Analysis.pbip
```

If Power BI Desktop was already open before external TMDL edits, close and reopen it before testing.
