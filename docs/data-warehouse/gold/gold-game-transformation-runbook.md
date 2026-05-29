# Gold Game Transformation Runbook

## Purpose

Run the Gold game transformation from Silver game Parquet into the semantic-model-ready game star schema.

Related implementation:

```text
src/data_warehouse/transforms/build_gold_game.py
```

## Inputs

- Silver game Parquet for one `source_month`.
- Silver dimensions:
  - `dim_time_control.parquet`
  - `dim_termination.parquet`
  - `dim_rating_difference_bucket.parquet`
- Python environment with `pyarrow` installed.

## Pilot Command

```powershell
.venv\Scripts\python.exe src\data_warehouse\transforms\build_gold_game.py `
  --source-month 2013-01 `
  --output-root data
```

Optional override:

```powershell
--silver-input data\silver\game\source_month=2013-01\silver_game.parquet
```

## Outputs

```text
data/gold/game/source_month=2013-01/fact_game.parquet
data/gold/dimensions/dim_date.parquet
data/gold/dimensions/dim_white_rating.parquet
data/gold/dimensions/dim_black_rating.parquet
data/gold/dimensions/dim_time_control.parquet
data/gold/dimensions/dim_termination.parquet
data/gold/dimensions/dim_rating_difference_bucket.parquet
data/gold/dimensions/dim_eco.parquet
data/gold/dimensions/dim_opening_variation.parquet
data/gold/manifests/source_month=2013-01/gold_game_manifest.json
```

## Transform Scope

The Gold transform:

- Builds `fact_game` at game grain.
- Writes only the requested `source_month` fact partition.
- Rebuilds dimensions globally from all available Silver game partitions.
- Builds `dim_date` from Silver `GameDate`.
- Builds separate `dim_white_rating` and `dim_black_rating` role-playing dimensions.
- Rebuilds `dim_time_control` and `dim_termination` from Silver game fields.
- Promotes static `dim_rating_difference_bucket`.
- Builds `dim_eco` from observed ECO codes.
- Builds `dim_opening_variation` from observed Lichess opening names and relates each variation to `dim_eco`.
- Writes explicit Parquet schemas with `zstd` compression.
- Writes a Gold transform manifest.

The transform does not build player, move-grain, FEN, engine-evaluation, or ML outputs.

## Validation

Validation is split into row validation and schema validation.

Row validation checks:

- Fact row count equals Silver row count.
- `SourceGameID` is populated and unique.
- Fact rows map to all required dimensions.
- ECO and opening variation mappings are covered.

Schema validation checks:

- `fact_game` and all Gold dimensions match the expected `gold-game-v1` physical schema.

## First Validated Pilot Result

```text
ValidationStatus = pass
SilverRowsRead = 121332
FactRowsWritten = 121332
DimDateRowsWritten = 32
DimWhiteRatingRowsWritten = 1346
DimBlackRatingRowsWritten = 1358
DimECORowsWritten = 412
DimOpeningVariationRowsWritten = 1847
UnmappedECORows = 0
UnmappedOpeningRows = 0
```

## Second-Month Validated Result

After processing `2013-01` and `2013-02`, Gold dimensions were rebuilt from both Silver partitions.

```text
SourceMonth = 2013-02
ValidationStatus = pass
SilverRowsRead = 123961
FactRowsWritten = 123961
AllSilverRowsReadForDimensions = 245293
DimDateRowsWritten = 60
DimWhiteRatingRowsWritten = 1436
DimBlackRatingRowsWritten = 1449
DimECORowsWritten = 438
DimOpeningVariationRowsWritten = 2077
UnmappedECORows = 0
UnmappedOpeningRows = 0
```

## Output Sizes From Pilot

```text
fact_game.parquet = 2055311 bytes
dim_date.parquet = 2771 bytes
dim_white_rating.parquet = 6615 bytes
dim_black_rating.parquet = 6654 bytes
dim_time_control.parquet = 9447 bytes
dim_termination.parquet = 1775 bytes
dim_rating_difference_bucket.parquet = 2013 bytes
dim_eco.parquet = 6191 bytes
dim_opening_variation.parquet = 42690 bytes
```

## Notes

Gold is the first layer intended to look like a Power BI semantic model source.

Keep `fact_game` narrow. Long descriptive text belongs in dimensions.

Global dimensions are rebuilt from all currently available Silver game partitions during the local prototype.
