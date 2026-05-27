# Source To Target: Game Fact

## Purpose

Define the initial source-to-target mapping for the game-grain fact and its candidate dimensions.

This document is intentionally focused on `fact_game`. Move-grain mapping belongs in a separate artifact.

## Grain

One row represents one chess game from the Lichess standard rated source.

The source natural key is the Lichess game id derived from the `Site` PGN header.

## Current Sample Row

| Source Field | Raw Example |
|---|---|
| `Site` | `https://lichess.org/j1dkb5dw` |
| `UTCDate` | `2012.12.31` |
| `UTCTime` | `23:01:03` |
| `White` | `BFG9k` |
| `Black` | `mamalak` |
| `Result` | `1-0` |
| `WhiteElo` | `1639` |
| `BlackElo` | `1403` |
| `WhiteRatingDiff` | `+5` |
| `BlackRatingDiff` | `-8` |
| `ECO` | `C00` |
| `Opening` | `French Defense: Normal Variation` |
| `TimeControl` | `600+8` |
| `Termination` | `Normal` |

## Source-To-Target Mapping

| Source Field | Bronze Field | Bronze Type | Silver/Gold Treatment | Keep/Drop | Transformation | Validation Candidate | Notes |
|---|---|---|---|---|---|---|---|
| `Site` | `site_url` | string | Drop from Gold after deriving game id | Bronze only | Preserve raw URL | Not null when game id is required | Useful for lineage/debug |
| `Site` | `source_game_id` | string | Keep as natural key; may be hidden in semantic model | Keep | Extract final path segment from URL | Not null; unique within source month | Needed to join game grain to move grain |
| none | `game_key` | bigint/int | Surrogate key in warehouse | Keep | Generated during warehouse load | Unique; stable within warehouse | Preferred fact key for joins after load |
| `UTCDate` | `utc_date_raw` | string | Convert to `game_date` and `date_key` | Keep transformed | Parse `yyyy.MM.dd` to date | Valid date or quarantine row | Consider date dimension later |
| `UTCTime` | `utc_time_raw` | string | Likely drop from Gold | Bronze only for now | Preserve raw value | Valid time format when populated | Not needed for first analytics pass |
| `White` | `white_player_name` | string | Replace with `white_player_key` | Dimension | Preserve raw value in Bronze; load to `dim_player` later | Not blank; unknown handling needed | Text cost may be high but player behavior may matter |
| `Black` | `black_player_name` | string | Replace with `black_player_key` | Dimension | Preserve raw value in Bronze; load to `dim_player` later | Not blank; unknown handling needed | Same dimension role-played twice |
| `Result` | `result_raw` | string | Replace with `result_key` and score columns | Dimension or small code | Map `1-0`, `0-1`, `1/2-1/2` | Must be one known result code | Proposed code: 0 draw, 1 white win, 2 black win |
| `Result` | `white_score` | decimal | Keep in fact or result dimension | Keep | `1-0` = 1.0; `1/2-1/2` = 0.5; `0-1` = 0.0 | Between 0 and 1 | Useful for score percentage |
| `Result` | `black_score` | decimal | Keep in fact or result dimension | Keep | `1-0` = 0.0; `1/2-1/2` = 0.5; `0-1` = 1.0 | Between 0 and 1 | Useful for black score percentage |
| `WhiteElo` | `white_elo_raw` | string | Convert to `white_elo` integer | Keep transformed | Strip/parse integer | Integer or unknown sentinel | Add rating band later |
| `BlackElo` | `black_elo_raw` | string | Convert to `black_elo` integer | Keep transformed | Strip/parse integer | Integer or unknown sentinel | Add rating band later |
| `WhiteRatingDiff` | `white_rating_diff_raw` | string | Drop from Gold for now | Bronze only | Preserve raw value | Optional signed integer if present | Not needed for current analysis |
| `BlackRatingDiff` | `black_rating_diff_raw` | string | Drop from Gold for now | Bronze only | Preserve raw value | Optional signed integer if present | Not needed for current analysis |
| `ECO` | `eco_code` | string | Replace with `eco_key` | Dimension | Preserve code; load `dim_eco` | Code pattern should be profiled, not assumed | ECO is the stable parent opening classification |
| `Opening` | `opening_name` | string | Replace with `opening_variation_key` | Dimension | Preserve raw Lichess text; load `dim_opening_variation` | Not blank rate should be tracked | Lichess is authoritative for observed variation labels |
| `TimeControl` | `time_control_raw` | string | Replace with `time_control_key`; keep parsed numeric fields if useful | Dimension | Parse initial/increment/delay/correspondence patterns | Known pattern or quarantine/unknown | Needs more profiling across months |
| `Termination` | `termination_raw` | string | Candidate `termination_key` | Dimension candidate | Preserve raw value; profile distinct values | Known value or unknown bucket | 2013-01 only showed `Normal` and `Time forfeit` |
| derived | `source_month` | string | Keep | Keep | From source file/month | Must match ingestion manifest | Partition and lineage column |
| derived | `source_file_sha256` | string | Keep in Bronze; may drop from Gold | Bronze/lineage | From compressed source file hash | Must match manifest | Supports raw-file deletion strategy |
| derived | `ingestion_run_id` | string | Keep in Bronze; may drop from Gold | Bronze/lineage | Generated per run | Must match manifest | Supports audit/debug |

## Candidate Dimensions

| Dimension | Grain | Key In Fact | Notes |
|---|---|---|---|
| `dim_player` | One row per distinct Lichess player name or player id | `white_player_key`, `black_player_key` | Role-playing dimension; may need bot/closed-account handling later |
| `dim_result` | One row per game result code | `result_key` | Avoids magic numbers and stores white/black scores |
| `dim_eco` | One row per ECO code | `eco_key` | Stable parent opening classification |
| `dim_opening_variation` | One row per distinct Lichess opening variation under an ECO code | `opening_variation_key` | Connects to `dim_eco`; keeps long text out of fact |
| `dim_time_control` | One row per distinct parsed time control pattern | `time_control_key` | Stores raw value, initial seconds, increment seconds, delay seconds, type, and class |
| `dim_termination` | One row per termination value | `termination_key` | Keep candidate until more months are profiled |
| `dim_date` | One row per calendar date | `date_key` | Optional, but likely useful for Power BI |

## Time Control Parsing Notes

For `600+8`:

| Attribute | Value |
|---|---|
| `initial_seconds` | `600` |
| `increment_seconds` | `8` |
| `delay_seconds` | null |
| `time_control_type` | `increment` |

Open issue: confirm whether Lichess PGN exports encode delay time controls differently or at all.

## Opening Modeling Notes

ECO is treated as the stable parent opening classification.

Lichess `Opening` is treated as the authoritative source for observed opening variation labels in this dataset.

External ECO references may enrich `dim_eco`, but should not overwrite Lichess variation names unless a reviewed mapping rule exists.

Initial hierarchy:

```text
dim_eco -> dim_opening_variation -> fact_game
```

Proposed dimension attributes:

```text
dim_eco
- eco_key
- eco_code
- eco_volume
- parent_opening_name

dim_opening_variation
- opening_variation_key
- eco_key
- lichess_opening_name
- normalized_opening_name
- mapping_status
```

## Derived Validation Candidates

Validation rules should be generated from the source-to-target contract.

Initial candidates:

- `source_game_id` is populated for every parsed game.
- `source_game_id` is unique within a source month.
- `game_date` parses from `UTCDate`.
- `Result` maps to one known result value.
- `WhiteElo` and `BlackElo` parse to integers when populated.
- `TimeControl` is either parsed into a known pattern or assigned an unknown/quarantine status.
- `ECO` and `Opening` missingness is measured by source month.
- `Termination` distinct values are profiled by source month.
- Bronze game row count reconciles to parser count and ingestion manifest.
- Bronze game rows can join to Bronze move rows by `source_game_id`.

## Open Decisions

- Should `white_score` and `black_score` live directly on `fact_game`, only in `dim_result`, or both?
- Should player names be retained in Gold, hashed, or only represented by surrogate keys?
- Should `UTCTime` be retained for potential time-of-day behavior analysis?
- Should rating diffs remain Bronze only, or support a future rating volatility analysis?
- Should `Termination` become a dimension immediately or remain a profiled text field until more months are inspected?
- Should unknown/invalid parse values go to quarantine tables or stay in Bronze with error flags?

