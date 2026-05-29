# Bronze Game Ingestion Runbook

## Purpose

Run the Bronze game-grain ingestion script for a Lichess monthly PGN export.

Related implementation:

```text
src/data_warehouse/ingestion/ingest_bronze_game.py
```

Related design:

```text
docs/data-warehouse/bronze/bronze-game-ingestion-guide.md
```

## Inputs

- A downloaded monthly `.pgn.zst` file.
- Python environment with `requirements.txt` installed.
- Source month, source dataset, and source URL.

## First Pilot Command

```powershell
.venv\Scripts\python.exe src\data_warehouse\ingestion\ingest_bronze_game.py `
  --input data\raw\lichess\standard\2013-01\lichess_db_standard_rated_2013-01.pgn.zst `
  --source-month 2013-01 `
  --source-dataset standard_rated `
  --source-url https://database.lichess.org/standard/lichess_db_standard_rated_2013-01.pgn.zst `
  --output-root data
```

## Parser Scope

This script is a game-grain Bronze parser. It does not reconstruct legal board states.

The parser:

- Streams the compressed `.pgn.zst` file.
- Preserves the first N decompressed PGN game blocks as the raw audit sample.
- Extracts PGN tag pairs into game-level columns.
- Computes `PlyCount` from movetext tokens without validating move legality.
- Enforces explicit PyArrow schemas for Bronze game and raw sample outputs.
- Writes Parquet with `zstd` compression.

This is intentional. Full legal move parsing is significantly slower and belongs in a separate move-grain pipeline after the required move-level facts are defined.

## Outputs

```text
data/bronze/game/source_month=2013-01/bronze_game.parquet
data/samples/raw_game_sample/source_month=2013-01/raw_game_sample.parquet
data/bronze/manifests/source_month=2013-01/ingestion_manifest.json
```

## Validation

The script writes validation status and messages to the ingestion manifest.

Minimum expected pilot result:

```text
ValidationStatus = pass
RawGameSampleRowsWritten = 10
BronzeGameRowsWritten > 0
GamesFailed = 0
bronze_game schema matches the expected schema contract
raw_game_sample schema matches the expected schema contract
```

Validation is split into two concerns:

- Row validation checks source completeness, ID uniqueness, result mappings, score arithmetic, win/draw flags, and rating difference sanity.
- Schema validation checks that written Parquet columns match the expected physical data types.

First validated pilot result for `2013-01`:

```text
ValidationStatus = pass
BronzeGameRowsWritten = 121332
RawGameSampleRowsWritten = 10
GamesFailed = 0
BronzeGameParquetBytes = 4274102
RawGameSampleParquetBytes = 10120
ManifestBytes = 1145
```

## Side Effects

- Writes Parquet outputs with `zstd` compression.
- Writes an ingestion manifest JSON file.
- Does not delete the raw `.pgn.zst` file.

## Notes

Raw file deletion is intentionally not performed by the first implementation. The deletion rule remains documented in the Bronze guide and raw game sample strategy.
