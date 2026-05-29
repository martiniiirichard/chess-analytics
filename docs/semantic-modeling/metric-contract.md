# Metric Contract

## Purpose

Define the analytical metrics before building ingestion, warehouse, semantic model, or Power BI assets.

Metrics can change what data must be captured, what grain is required, which dimensions are needed, and whether move-level, clock, evaluation, or position-derived fields are necessary.

## Metric Design Principles

- Start with the business question before the measure name.
- Declare the required grain: game, move/ply, position/evaluation, endgame transition, or aggregate.
- Identify source fields and derived fields before coding ingestion.
- Record filters and caveats explicitly.
- Keep v1 metrics practical and game-grain where possible.
- Treat move-grain, engine-eval, clock, and endgame metrics as later phases unless they are required by the metric.

## Metric Contract Template

| Field | Description |
|---|---|
| `metric_name` | Human-readable metric name |
| `business_question` | Decision or analysis this metric supports |
| `grain_required` | Lowest grain needed to calculate correctly |
| `definition` | Business definition in plain language |
| `calculation` | Formula or pseudo-formula |
| `source_fields_needed` | Raw fields needed from PGN or derived source |
| `derived_fields_needed` | Fields produced during Bronze/Silver/Gold processing |
| `dimensions` | Dimensions needed for slicing |
| `filters` | Required or recommended filters |
| `known_limitations` | Caveats, bias, sparsity, or source issues |
| `implementation_phase` | v1, v2, v3, or research |
| `open_questions_for_martin` | Domain decisions needed before implementation |

## V1 Game-Grain Metrics

| Metric | Business Question | Grain Required | Core Fields | Dimensions | Notes |
|---|---|---|---|---|---|
| Game Count | How many games are in the selected filter context? | Game | `source_game_id` | All game dimensions | Base measure for opening popularity, time-control mix, rating distribution, and rate denominators |
| White Score % | How well does White score across the selected population? | Game | `result_raw`, `white_score` | Date, time control, rating band, opening | Score convention: win = 1, draw = 0.5, loss = 0 |
| Black Score % | How well does Black score across the selected population? | Game | `result_raw`, `black_score` | Date, time control, rating band, opening | Same convention from Black perspective |
| Draw Rate | How often do games end in draws? | Game | `result_raw` | Date, time control, rating band, opening | Useful because draw rate changes sharply by pool |
| Opening Score % | Which openings perform best by side? | Game | `white_score`, `black_score`, opening keys | ECO, opening variation, side, time control, rating band | Semantic/report-context measure using White/Black Score % |
| Time Control Mix | What types of games are in the data? | Game | `time_control_raw` | Time control, time-control class, date | Requires parsing initial/increment/delay/correspondence |
| Time Forfeit Count | How many games ended by time forfeit? | Game | `termination_raw` | Time control, rating band, date, termination | Derived from `Termination = Time forfeit` |
| Time Forfeit Rate | How often do games end by time forfeit? | Game | `termination_raw` | Time control, rating band, date, termination | Important because time forfeits are common in the sample |

## Official Metric Definitions

### Game Count

Business question: How many games are in the selected filter context?

Grain required: game.

Definition: count of rows in `fact_game` after report filters are applied.

DAX:

```DAX
Game Count = COUNTROWS('fact_game')
```

Modeling rule: do not add a physical `game_count = 1` helper column to `fact_game`; use the semantic model measure.

Validation rule:

```text
Game Count = Bronze game row count for the selected load/month
```

Reporting patterns:

- Opening popularity = `Game Count` by ECO or opening variation.
- Time control mix = `Game Count` by time control.
- Rating distribution = `Game Count` by rating band.
- Termination distribution = `Game Count` by termination.

### White Score %

Business question: How well does White score across the selected population?

Grain required: game.

Definition: average score earned by White, where a White win is worth 1.0, a draw is worth 0.5, and a White loss is worth 0.0.

Calculation:

```text
White Score % = SUM(white_score) / COUNT(source_game_id)
```

Result mapping:

| `result_raw` | `white_score` |
|---|---:|
| `1-0` | 1.0 |
| `1/2-1/2` | 0.5 |
| `0-1` | 0.0 |

Validation rule:

```text
White Score % + Black Score % = 100%
```

### Black Score %

Business question: How well does Black score across the selected population?

Grain required: game.

Definition: average score earned by Black, where a Black win is worth 1.0, a draw is worth 0.5, and a Black loss is worth 0.0.

Calculation:

```text
Black Score % = SUM(black_score) / COUNT(source_game_id)
```

Result mapping:

| `result_raw` | `black_score` |
|---|---:|
| `1-0` | 0.0 |
| `1/2-1/2` | 0.5 |
| `0-1` | 1.0 |

Validation rules:

```text
White Score % + Black Score % = 100%
```

```text
white_score + black_score = 1.0 for every completed game
```

### Draw Rate

Business question: How often do games end in draws across the selected population?

Grain required: game.

Definition: percentage of completed games where the result is a draw.

Calculation:

```text
Draw Rate = SUM(is_draw) / COUNT(source_game_id)
```

Result mapping:

| `result_raw` | `is_draw` |
|---|---:|
| `1-0` | 0 |
| `1/2-1/2` | 1 |
| `0-1` | 0 |

Known limitations:

- Draw rate is heavily affected by rating band and time control.
- Bullet and blitz games may have materially different draw behavior from rapid, classical, or high-rating games.

Validation rule:

```text
White Win Rate + Black Win Rate + Draw Rate = 100%
```

### White Win Rate

Business question: How often does White win across the selected population?

Grain required: game.

Definition: percentage of completed games where White wins.

Calculation:

```text
White Win Rate = SUM(is_white_win) / COUNT(source_game_id)
```

Result mapping:

| `result_raw` | `is_white_win` |
|---|---:|
| `1-0` | 1 |
| `1/2-1/2` | 0 |
| `0-1` | 0 |

### Black Win Rate

Business question: How often does Black win across the selected population?

Grain required: game.

Definition: percentage of completed games where Black wins.

Calculation:

```text
Black Win Rate = SUM(is_black_win) / COUNT(source_game_id)
```

Result mapping:

| `result_raw` | `is_black_win` |
|---|---:|
| `1-0` | 0 |
| `1/2-1/2` | 0 |
| `0-1` | 1 |

Validation rule:

```text
White Win Rate + Black Win Rate + Draw Rate = 100%
```

### Opening Score %

Business question: Which openings or opening variations perform best by side?

Grain required: game.

Definition: score percentage evaluated in an opening-filtered report context.

DAX pattern:

```DAX
White Opening Score % = [White Score %]
Black Opening Score % = [Black Score %]
```

Required filter context:

- `dim_eco`
- `dim_opening_variation`

Modeling rule: do not create separate ingestion fields for opening score. This is a semantic/reporting measure over `White Score %`, `Black Score %`, `Game Count`, and the opening dimensions.

Guardrail:

```text
Only interpret opening score when [Game Count] meets the agreed minimum sample threshold.
```

Potential helper measure:

```DAX
Opening Sample Warning =
IF(
    [Game Count] < 100,
    "Low sample size",
    BLANK()
)
```

### Time Forfeit Count

Business question: How many games ended by time forfeit in the selected population?

Grain required: game.

Definition: count of games where the source termination value is `Time forfeit`.

DAX pattern:

```DAX
Time Forfeit Count =
CALCULATE(
    [Game Count],
    'dim_termination'[IsTimeForfeit] = TRUE()
)
```

Source mapping:

| `termination_raw` | `IsTimeForfeit` |
|---|---:|
| `Time forfeit` | 1 |
| other known values | 0 |

### Time Forfeit Rate

Business question: How often do games end by time forfeit in the selected population?

Grain required: game.

Definition: percentage of games where the source termination value is `Time forfeit`.

DAX pattern:

```DAX
Time Forfeit Rate =
DIVIDE(
    [Time Forfeit Count],
    [Game Count]
)
```

Known limitations:

- Termination values should be profiled by source month because later months may include values not present in 2013-01.
- Time forfeit behavior should usually be interpreted by time-control class.

## V2 Move And Endgame Metrics

| Metric | Business Question | Grain Required | Core Fields | Dimensions | Notes |
|---|---|---|---|---|---|
| Endgame Entry Rate | How often do games reach an endgame? | Move/position | Move list, material state, phase classification | Time control, rating band, opening | Requires Martin-defined endgame rules |
| Endgame Type Frequency | Which endgames occur most often? | Move/position | Material state, piece counts, endgame taxonomy | Endgame type, rating band, time control | Needs endgame taxonomy |
| Endgame Conversion Rate | How often does the advantaged side convert? | Move + game | Endgame start state, result, maybe eval/material advantage | Endgame type, side, rating band | Requires advantage definition |
| Recovery Rate | How often does the worse side recover? | Move/eval or move/material | Disadvantage threshold, later result | Time control, rating band, endgame type | Requires disadvantage/recovery definition |

## V3 Eval Or Engine Metrics

| Metric | Business Question | Grain Required | Core Fields | Dimensions | Notes |
|---|---|---|---|---|---|
| Mistake Rate | How often do players make meaningful errors? | Move/eval | Eval before/after move, side to move | Phase, rating band, time control | Requires eval source and thresholds |
| Blunder Rate | How often do players make severe errors? | Move/eval | Eval delta, mate score handling | Phase, rating band, time control | Must define threshold and mate logic |
| Missed Win Rate | How often does a player fail to convert a winning chance? | Move/eval | Eval threshold, result, later eval path | Phase, endgame type, rating band | Research metric |
| Time Pressure Error Rate | Do errors increase near low clock states? | Move/eval/clock | Eval delta, clock remaining | Time control, phase, rating band | Requires modern data with clock comments |

## Ingestion Implications

| Requirement | Driven By | Implication |
|---|---|---|
| Game-grain row count | Game Count and all rate denominators | `fact_game` must contain one row per game and support `COUNTROWS` |
| Game-grain result parsing | Score %, win rates, draw rate, opening score | `fact_game` can support v1 metrics |
| ECO/opening dimensions | Opening popularity reporting pattern and opening score | Use `dim_eco` as parent classification and `dim_opening_variation` from observed Lichess opening labels; opening score is a semantic/report-context measure |
| Time-control parsing | Time control mix and filters | Need parsed numeric fields and class/type |
| Termination parsing | Time Forfeit Count and Time Forfeit Rate | Need `dim_termination` with `IsTimeForfeit` |
| Move-grain rows | Endgame and phase metrics | `fact_move` required for v2 |
| Material/phase derivation | Endgame metrics | Need board replay, but not full FEN persistence by default |
| Eval source | Mistake/blunder metrics | Need Lichess eval comments, separate eval data, or engine pass |
| Clock source | Time pressure metrics | Need newer PGN months with clock comments |

## Open Questions For Martin

- Which v1 metrics matter most for the first Power BI prototype?
- What sample-size threshold should opening performance require?
- Should opening score be reported from White/Black perspective, opening-player perspective, or both?
- How should rating bands be defined?
- Which time-control classes matter for chess usefulness versus data convenience?
- Should bot games be excluded when player-improvement analysis begins?
- What is the first practical definition of an endgame?
- What mistake thresholds are meaningful for chess improvement, not just engine math?
