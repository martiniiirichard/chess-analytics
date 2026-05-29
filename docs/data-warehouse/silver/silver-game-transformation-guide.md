# Silver Game Transformation Guide

## Purpose

Define the first Silver transformation from Bronze game output into typed, conformed, warehouse-ready game data.

Silver is where source-shaped PGN fields become analytics-shaped columns and dimension keys. Gold should not need to parse raw PGN strings.

## Scope

Initial input:

```text
data/bronze/game/source_month=YYYY-MM/bronze_game.parquet
```

Initial outputs:

```text
data/silver/game/source_month=YYYY-MM/silver_game.parquet
data/silver/dimensions/dim_time_control.parquet
data/silver/dimensions/dim_termination.parquet
data/silver/dimensions/dim_rating_difference_bucket.parquet
```

Later outputs:

```text
data/silver/dimensions/dim_white_rating.parquet
data/silver/dimensions/dim_black_rating.parquet
data/silver/dimensions/dim_eco.parquet
data/silver/dimensions/dim_opening_variation.parquet
data/silver/dimensions/dim_player.parquet
```

## Grain

`silver_game` remains one row per Lichess game.

Natural key:

```text
SourceGameID
```

## Transformation Rules

| Bronze Column | Silver Column | Rule |
|---|---|---|
| `SourceGameID` | `SourceGameID` | Preserve natural key |
| `UTCDateRaw` | `GameDate` | Parse `yyyy.MM.dd` to date |
| `UTCDateRaw` | `Date_SK` | Convert parsed date to `yyyymmdd` integer |
| `ResultRaw` | `ResultCode` | Preserve known result code |
| `WhiteScore` | `WhiteScore` | Preserve numeric score |
| `BlackScore` | `BlackScore` | Preserve numeric score |
| `IsWhiteWin` | `IsWhiteWin` | Preserve integer flag |
| `IsBlackWin` | `IsBlackWin` | Preserve integer flag |
| `IsDraw` | `IsDraw` | Preserve integer flag |
| `WhiteRating_SK` | `WhiteRating_SK` | Preserve role-specific rating key |
| `BlackRating_SK` | `BlackRating_SK` | Preserve role-specific rating key |
| `AbsRatingDifference` | `AbsRatingDifference` | Preserve derived absolute gap |
| `RatingDifferenceBucket_SK` | `RatingDifferenceBucket_SK` | Preserve bucket relationship key |
| `TimeControlRaw` | `TimeControlRaw` | Preserve for lineage and mapping audit |
| `TimeControlRaw` | `TimeControl_SK` | Map to `dim_time_control` |
| `TerminationRaw` | `Termination_SK` | Map to `dim_termination` |
| `TerminationRaw` | `IsTimeForfeit` | `1` when `TerminationRaw = Time forfeit`, else `0` |
| `ECOCode` | `ECOCode` | Preserve until opening dimensions are finalized |
| `OpeningName` | `OpeningName` | Preserve until opening dimensions are finalized |
| `PlyCount` | `PlyCount` | Preserve approximate Bronze ply count |
| `SourceMonth` | `SourceMonth` | Preserve partition and lineage |
| `IngestionRunID` | `BronzeIngestionRunID` | Preserve lineage |

## Time Control Parsing

Accepted v1 source pattern:

```text
InitialSeconds+IncrementSeconds
```

Example:

```text
600+8
```

Silver attributes:

| Column | Rule |
|---|---|
| `InitialSeconds` | Integer before `+` |
| `IncrementSeconds` | Integer after `+` |
| `EstimatedGameSeconds` | `InitialSeconds + (40 * IncrementSeconds)` |
| `TimeControlClass` | Bullet, Blitz, Rapid, Classical, or Unknown |
| `TimeControlType` | `increment` or `unknown` |
| `IsParsed` | `1` when pattern parses, else `0` |

Classification:

| TimeControlClass | Rule |
|---|---|
| `Bullet` | `EstimatedGameSeconds < 180` |
| `Blitz` | `180 <= EstimatedGameSeconds < 480` |
| `Rapid` | `480 <= EstimatedGameSeconds < 1500` |
| `Classical` | `EstimatedGameSeconds >= 1500` |
| `Unknown` | Missing, `-`, or unparsable |

## Dimension Seeds

### `dim_time_control`

Grain: one row per distinct `TimeControlRaw` value.

Candidate columns:

| Column | Rule |
|---|---|
| `TimeControl_SK` | Stable surrogate key for raw time-control value |
| `TimeControlRaw` | Original Lichess value |
| `InitialSeconds` | Parsed integer or null |
| `IncrementSeconds` | Parsed integer or null |
| `EstimatedGameSeconds` | Derived integer or null |
| `TimeControlClass` | Accepted v1 class |
| `TimeControlType` | `increment` or `unknown` |
| `IsParsed` | Integer flag |

### `dim_termination`

Grain: one row per distinct `TerminationRaw` value.

Candidate columns:

| Column | Rule |
|---|---|
| `Termination_SK` | Stable surrogate key |
| `TerminationRaw` | Source value |
| `TerminationLabel` | Display label |
| `IsTimeForfeit` | `1` for `Time forfeit`, else `0` |
| `MappingStatus` | `mapped`, `unknown`, or `review_needed` |

### `dim_rating_difference_bucket`

Grain: one row per approved rating difference bucket.

Candidate rows:

| `RatingDifferenceBucket_SK` | Label |
|---:|---|
| 1 | `0-49 roughly equal` |
| 2 | `50-99 small edge` |
| 3 | `100-199 meaningful edge` |
| 4 | `200-399 large edge` |
| 5 | `400-599 very large edge` |
| 6 | `600+ extreme mismatch` |
| 0 | `Unknown` |

## Silver Validation

Minimum checks:

| Check | Rule |
|---|---|
| Row count | `silver_game` row count equals Bronze game row count for the same `source_month` |
| Source key | `SourceGameID` populated and unique within `source_month` |
| Date parse | `GameDate` populated for valid `UTCDateRaw` |
| Date key | `Date_SK` is integer `yyyymmdd` when `GameDate` exists |
| Result score | `WhiteScore + BlackScore = 1.0` |
| Result flags | `IsWhiteWin + IsBlackWin + IsDraw = 1` |
| Rating difference | `AbsRatingDifference >= 0` when populated |
| Time control key | Every `silver_game.TimeControl_SK` maps to `dim_time_control.TimeControl_SK` |
| Termination key | Every `silver_game.Termination_SK` maps to `dim_termination.Termination_SK` |
| Unknown counts | Unknown/unparsed values are counted by `source_month` |
| Schema | Written Parquet schema matches the Silver v1 contract |

## Gold Handoff

Silver should provide enough clean data for Gold to build:

```text
fact_game
dim_date
dim_time_control
dim_termination
dim_rating_difference_bucket
dim_white_rating
dim_black_rating
dim_eco
dim_opening_variation
```

Gold should remove raw lineage/debug fields unless they are needed for audit or drillthrough.

## Open Decisions

- How to generate stable surrogate keys for dimensions locally while preserving cloud portability.
- Whether unknown keys use `0` consistently across all dimensions.
- Whether opening dimensions are built in the first Silver script or deferred until Gold.
- Whether player dimensions are deferred until a player-analysis use case is approved.
- Whether `PlyCount` remains in `fact_game` or moves to a game statistics dimension later.
