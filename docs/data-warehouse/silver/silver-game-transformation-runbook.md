# Silver Game Transformation Runbook

## Purpose

Run the Silver game transformation from Bronze game Parquet into typed, conformed Silver outputs.

Related implementation:

```text
src/data_warehouse/transforms/build_silver_game.py
```

Related design:

```text
docs/data-warehouse/silver/silver-game-transformation-guide.md
```

## Inputs

- Bronze game Parquet for one `source_month`.
- Python environment with `requirements.txt` installed.

## First Pilot Command

```powershell
.venv\Scripts\python.exe src\data_warehouse\transforms\build_silver_game.py `
  --source-month 2013-01 `
  --output-root data
```

Optional override:

```powershell
--bronze-input data\bronze\game\source_month=2013-01\bronze_game.parquet
```

## Outputs

```text
data/silver/game/source_month=2013-01/silver_game.parquet
data/silver/dimensions/dim_time_control.parquet
data/silver/dimensions/dim_termination.parquet
data/silver/dimensions/dim_rating_difference_bucket.parquet
data/silver/manifests/source_month=2013-01/silver_game_manifest.json
```

## Transform Scope

The first Silver transform:

- Parses `UTCDateRaw` into `GameDate` and `Date_SK`.
- Preserves additive result fields needed for semantic measures.
- Parses Lichess increment-style `TimeControlRaw` values.
- Creates `dim_time_control`.
- Creates `dim_termination`.
- Creates static `dim_rating_difference_bucket`.
- Preserves opening fields until opening dimensions are implemented.
- Preserves Bronze ingestion lineage as `BronzeIngestionRunID`.

## Validation

The script writes validation status and messages to the Silver manifest.

Validation is split into two concerns:

- Row validation checks row count reconciliation, source key uniqueness, score arithmetic, result flags, non-negative rating differences, and dimension key coverage.
- Schema validation checks that written Parquet columns match the expected physical data types.

Minimum expected pilot result:

```text
ValidationStatus = pass
BronzeRowsRead = 121332
SilverRowsWritten = 121332
UnknownTimeControlRows = 266
TimeForfeitRows = 37883
silver_game schema matches the expected schema contract
dim_time_control schema matches the expected schema contract
dim_termination schema matches the expected schema contract
dim_rating_difference_bucket schema matches the expected schema contract
```

First validated pilot result for `2013-01`:

```text
ValidationStatus = pass
BronzeRowsRead = 121332
SilverRowsWritten = 121332
InvalidDateRows = 0
UnknownTimeControlRows = 266
UnknownTerminationRows = 0
TimeForfeitRows = 37883
DimTimeControlRowsWritten = 396
DimTerminationRowsWritten = 2
DimRatingDifferenceBucketRowsWritten = 7
SilverGameParquetBytes = 2210510
DimTimeControlParquetBytes = 9447
DimTerminationParquetBytes = 1775
DimRatingDifferenceBucketParquetBytes = 2013
ManifestBytes = 1875
```

## Side Effects

- Writes Parquet outputs with `zstd` compression.
- Writes a Silver transform manifest JSON file.
- Does not modify Bronze outputs.
- Does not delete raw source files.

## Notes

Dimension keys are deterministic for parsed time controls and terminations. Unknown/unparsed values use key `0`.

This is still a local prototype. The validation pattern should transfer directly to Fabric or Databricks notebooks later.
