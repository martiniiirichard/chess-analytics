# Time Control Dimensions

## Purpose

Define how Lichess `TimeControl` PGN values should be parsed, classified, and modeled.

This is a Silver-layer transformation and semantic modeling decision, not a metric.

## Source Pattern

Lichess standard rated PGN uses increment-style time controls in the observed sample:

```text
InitialSeconds+IncrementSeconds
```

Example:

```text
600+8
```

Meaning:

```text
InitialSeconds = 600
IncrementSeconds = 8
```

Each player starts with 600 seconds. After each move a player makes, 8 seconds are added to that player's clock.

## Modeling Decision

Use Lichess-style estimated duration for v1 classification:

```text
EstimatedGameSeconds = InitialSeconds + (40 * IncrementSeconds)
```

Accepted v1 classes:

| TimeControlClass | Rule |
|---|---|
| `Bullet` | `EstimatedGameSeconds < 180` |
| `Blitz` | `180 <= EstimatedGameSeconds < 480` |
| `Rapid` | `480 <= EstimatedGameSeconds < 1500` |
| `Classical` | `EstimatedGameSeconds >= 1500` |
| `Unknown` | Unparsable, missing, or `-` |

Do not include delay fields in v1. Delay has not been observed in the sample and Lichess account UI presents increment controls.

## Layer Treatment

| Layer | Field | Treatment |
|---|---|---|
| Bronze | `time_control_raw` | Preserve original PGN string |
| Silver | `InitialSeconds` | Split before `+`, cast to integer |
| Silver | `IncrementSeconds` | Split after `+`, cast to integer |
| Silver | `EstimatedGameSeconds` | `InitialSeconds + (40 * IncrementSeconds)` |
| Silver | `TimeControlClass` | Derived from estimated seconds |
| Silver/Gold | `TimeControl_SK` | Relationship key to `dim_time_control` |

## Candidate `dim_time_control`

Grain: one row per distinct parsed time-control pattern.

Candidate columns:

| Column | Purpose |
|---|---|
| `TimeControl_SK` | Surrogate key |
| `RawTimeControl` | Original PGN value such as `600+8` |
| `InitialSeconds` | Starting clock seconds |
| `IncrementSeconds` | Increment seconds added after each move |
| `EstimatedGameSeconds` | Lichess-style estimated duration |
| `TimeControlClass` | Bullet, Blitz, Rapid, Classical, Unknown |
| `TimeControlType` | `increment` or `unknown` |
| `IsParsed` | Boolean parse success flag |

## Validation Rules

- `time_control_raw` matches `^\d+\+\d+$` or maps to `Unknown`.
- `InitialSeconds` is an integer when parsed.
- `IncrementSeconds` is an integer when parsed.
- `EstimatedGameSeconds` is non-negative when parsed.
- `TimeControlClass` maps to one accepted class.
- Unknown/unparsed values are counted by source month.

## Caveat

Lichess time-control classes should not be compared directly to over-the-board chess classifications. Over-the-board chess has more variation and different classification conventions.

