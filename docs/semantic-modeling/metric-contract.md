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
| White Score % | How well does White score across the selected population? | Game | `result_raw`, `white_score` | Date, time control, rating band, opening | Score convention: win = 1, draw = 0.5, loss = 0 |
| Black Score % | How well does Black score across the selected population? | Game | `result_raw`, `black_score` | Date, time control, rating band, opening | Same convention from Black perspective |
| Draw Rate | How often do games end in draws? | Game | `result_raw` | Date, time control, rating band, opening | Useful because draw rate changes sharply by pool |
| Opening Popularity | Which openings occur most often? | Game | `eco_code`, `opening_name` | ECO, opening variation, time control, rating band | ECO is parent classification; Lichess Opening is variation label |
| Opening Score % | Which openings perform best by side? | Game | `result_raw`, `white_score`, `black_score`, `eco_code`, `opening_name` | ECO, opening variation, side, time control, rating band | Needs sample-size threshold |
| Time Control Mix | What types of games are in the data? | Game | `time_control_raw` | Time control, time-control class, date | Requires parsing initial/increment/delay/correspondence |
| Termination Rate | How do games end? | Game | `termination_raw` | Time control, rating band, date | Needs more profiling beyond 2013-01 |

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
| Game-grain result parsing | Score %, draw rate, opening score | `fact_game` can support v1 metrics |
| ECO/opening dimensions | Opening popularity and score | Use `dim_eco` as parent classification and `dim_opening_variation` from observed Lichess opening labels |
| Time-control parsing | Time control mix and filters | Need parsed numeric fields and class/type |
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
