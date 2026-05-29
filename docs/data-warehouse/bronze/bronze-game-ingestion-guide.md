# Bronze Game Ingestion Guide

## Purpose

Define the first implementation path for ingesting Lichess monthly PGN files into a Bronze game-grain output.

This guide is intentionally limited to game-grain ingestion. Move-grain ingestion belongs in a later guide after the `fact_game` contract is stable.

## Scope

Initial source:

```text
standard rated Lichess monthly PGN export
2013-01 pilot month
```

Initial output:

```text
bronze_game
raw_game_sample
ingestion_manifest
```

Out of scope for this guide:

- Move/ply rows
- FEN persistence
- Engine evaluation
- Clock/time-pressure analysis
- SQL warehouse load
- Power BI model build

## Design Rules

- Read `.pgn.zst` as a stream; do not fully decompress to disk.
- Preserve raw source fields in Bronze where they are cheap and useful for lineage.
- Do not persist generated per-ply FEN in Bronze game ingestion.
- Keep the source `TimeControl` value raw in Bronze; parse it in Silver.
- Keep the source `Termination` value raw in Bronze; map it through `dim_termination` later.
- Keep source ratings as raw strings and parsed numeric keys where valid.
- Use `SK_` suffix/prefix convention consistently for relationship keys, as documented in `AGENTS.md`.
- Capture `raw_game_sample` before deleting the monthly raw file.
- Write an ingestion manifest for every monthly run.

## Inputs

| Input | Example | Notes |
|---|---|---|
| Source URL | `https://database.lichess.org/standard/lichess_db_standard_rated_2013-01.pgn.zst` | Monthly file URL |
| Source month | `2013-01` | Derived from file name or run parameter |
| Source dataset | `standard_rated` | v1 dataset |
| Parser version | TBD | Should change when parsing logic changes |
| Schema version | TBD | Should change when output schema changes |

## Bronze Game Grain

One row represents one parsed PGN game.

Natural source key:

```text
SourceGameID
```

Derived from the final path segment of the Lichess `Site` header.

## Bronze Game Columns

Candidate v1 columns:

| Column | Type | Source | Notes |
|---|---|---|---|
| `SourceGameID` | string | `Site` | Final URL segment, e.g. `j1dkb5dw` |
| `SiteURL` | string | `Site` | Bronze lineage/debug field |
| `EventRaw` | string | `Event` | Preserve source event text |
| `UTCDateRaw` | string | `UTCDate` | Preserve raw date string |
| `UTCTimeRaw` | string | `UTCTime` | Preserve raw time string |
| `WhitePlayerName` | string | `White` | Candidate player dimension input |
| `BlackPlayerName` | string | `Black` | Candidate player dimension input |
| `ResultRaw` | string | `Result` | Source result |
| `WhiteScore` | decimal | derived | `1-0` = 1.0, draw = 0.5, `0-1` = 0.0 |
| `BlackScore` | decimal | derived | `1-0` = 0.0, draw = 0.5, `0-1` = 1.0 |
| `IsWhiteWin` | integer/boolean | derived | `1` when `ResultRaw = 1-0` |
| `IsBlackWin` | integer/boolean | derived | `1` when `ResultRaw = 0-1` |
| `IsDraw` | integer/boolean | derived | `1` when `ResultRaw = 1/2-1/2` |
| `WhiteEloRaw` | string | `WhiteElo` | Preserve source value |
| `BlackEloRaw` | string | `BlackElo` | Preserve source value |
| `WhiteRating_SK` | integer | derived | Parsed `WhiteElo`; key equals rating value when valid |
| `BlackRating_SK` | integer | derived | Parsed `BlackElo`; key equals rating value when valid |
| `AbsRatingDifference` | integer | derived | Absolute rating difference when both ratings are valid |
| `RatingDifferenceBucket_SK` | integer | derived | Bucket key for absolute rating difference |
| `WhiteRatingDiffRaw` | string | `WhiteRatingDiff` | Bronze only for now |
| `BlackRatingDiffRaw` | string | `BlackRatingDiff` | Bronze only for now |
| `ECOCode` | string | `ECO` | Parent opening classification source |
| `OpeningName` | string | `Opening` | Lichess observed variation label |
| `TimeControlRaw` | string | `TimeControl` | Preserve raw; Silver parses |
| `TerminationRaw` | string | `Termination` | Preserve raw; dimension maps later |
| `PlyCount` | integer | derived | Count of mainline plies |
| `SourceMonth` | string | run parameter | Partition/lineage |
| `SourceDataset` | string | run parameter | Example: `standard_rated` |
| `SourceFileName` | string | source file | Downloaded file name |
| `SourceFileSHA256` | string | derived | Hash of compressed source file |
| `IngestionRunID` | string | derived | Links outputs and manifest |
| `ParserVersion` | string | run parameter | Parser logic version |
| `SchemaVersion` | string | run parameter | Output schema version |

## Silver Handoff

Bronze game ingestion should produce enough data for Silver to derive:

```text
Date_SK
Result_SK
WhitePlayer_SK
BlackPlayer_SK
ECO_SK
OpeningVariation_SK
TimeControl_SK
Termination_SK
```

Silver will also validate and type:

```text
GameDate
InitialSeconds
IncrementSeconds
EstimatedGameSeconds
TimeControlClass
IsTimeForfeit
```

## Raw Game Sample

Before parsing the full file, capture the first `10` parseable raw PGNs into `raw_game_sample`.

Required fields are defined in:

```text
docs/data-warehouse/ingestion/raw-game-sample-strategy.md
```

## Ingestion Manifest

Every run should write a manifest with:

| Field | Purpose |
|---|---|
| `IngestionRunID` | Links all artifacts from one run |
| `SourceURL` | Original monthly URL |
| `SourceMonth` | Month represented by the file |
| `SourceDataset` | Dataset name |
| `SourceFileName` | Downloaded file name |
| `DownloadTimestampUTC` | Download time |
| `CompressedSizeBytes` | Raw `.pgn.zst` size |
| `SourceFileSHA256` | Hash of compressed source file |
| `ParserVersion` | Parser logic version |
| `SchemaVersion` | Output schema version |
| `GamesParsed` | Count of successfully parsed games |
| `GamesFailed` | Count of failed game parses |
| `BronzeGameRowsWritten` | Output row count |
| `RawGameSampleRowsWritten` | Raw PGN sample count |
| `ValidationStatus` | `pass`, `warning`, or `fail` |
| `ValidationMessages` | List of notable validation results |

## Validation Checks

Minimum validation checks:

| Check | Rule |
|---|---|
| Source file exists | Raw monthly file exists before parse |
| Source hash computed | SHA256 is populated |
| Raw sample captured | First 10 parseable PGNs captured unless file has fewer than 10 games |
| Game rows written | `BronzeGameRowsWritten > 0` |
| Parse failure rate | Below agreed threshold |
| Source game id populated | `SourceGameID` populated for parsed rows |
| Source game id uniqueness | Unique within `SourceMonth` |
| Result mapping | `ResultRaw` maps to scores and flags |
| Score sum | `WhiteScore + BlackScore = 1.0` for completed games |
| Win/draw flags | `IsWhiteWin + IsBlackWin + IsDraw = 1` for completed games |
| Rating parse | Valid ratings parse to integer keys or unknown/null |
| Rating difference | Non-negative when both ratings are valid |
| Time control raw populated | Raw value preserved, including `-` |
| Termination raw populated | Raw value preserved or unknown bucketed |
| Manifest written | Manifest exists and references output paths |

## Raw File Deletion Rule

The downloaded monthly raw file can be deleted without additional manual approval only when:

- Bronze game ingestion completed.
- Required validation checks passed.
- Ingestion manifest was written.
- Raw game sample was captured.
- No required step was skipped.

If any required step fails or is skipped, raw file deletion must pause and Martin must approve the next action.

## First Implementation Path

Recommended first script:

```text
src/data_warehouse/ingestion/ingest_bronze_game.py
```

Recommended first run:

```text
source_month = 2013-01
source_dataset = standard_rated
```

Recommended output paths:

```text
data/bronze/game/source_month=2013-01/bronze_game.parquet
data/samples/raw_game_sample/source_month=2013-01/raw_game_sample.parquet
data/bronze/manifests/source_month=2013-01/ingestion_manifest.json
```

