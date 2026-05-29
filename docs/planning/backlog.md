# Project Backlog

## Purpose

Capture ideas, follow-up decisions, and future work so they do not get lost in chat.

Use this backlog when asking "what next?"

## Status Values

| Status | Meaning |
|---|---|
| `Proposed` | Idea captured, not yet accepted |
| `Accepted` | Agreed direction, not started |
| `In Progress` | Currently being worked |
| `Blocked` | Needs decision, source data, tool access, or prerequisite |
| `Done` | Completed and documented |

## Priority Values

| Priority | Meaning |
|---|---|
| `P0` | Needed before next implementation step |
| `P1` | Important for v1 prototype |
| `P2` | Useful after v1 is stable |
| `Research` | Interesting later, not core path |

## Current Backlog

| ID | Item | Area | Status | Priority | Notes |
|---|---|---|---|---|---|
| CHESS-BL-001 | Finish v1 metric contract definitions | Semantic modeling | In Progress | P0 | Game Count, score %, win rates, draw rate, and opening score are underway |
| CHESS-BL-002 | Define time-control dimension | Semantic modeling | Done | P0 | Silver split of `time_control_raw`; classify using `InitialSeconds + (40 * IncrementSeconds)` |
| CHESS-BL-003 | Update source-to-target for time control | Semantic modeling | Done | P0 | Added `TimeControl_SK`, `InitialSeconds`, `IncrementSeconds`, `EstimatedGameSeconds`, and `TimeControlClass`; no delay in v1 |
| CHESS-BL-004 | Decide opening sample threshold | Semantic modeling | Proposed | P1 | Needed for Opening Score % guardrail |
| CHESS-BL-005 | Define move fact source-to-target | Semantic modeling | Proposed | P1 | Start after game-grain contract is stable |
| CHESS-BL-006 | Define endgame taxonomy v1 | Semantic modeling | Proposed | P2 | Needs Martin's chess-domain rules |
| CHESS-BL-007 | Define mistake/blunder taxonomy | Semantic modeling | Proposed | Research | Requires eval-source decision |
| CHESS-BL-008 | Decide eval source strategy | Data warehouse | Proposed | Research | Lichess eval comments, separate eval data, or engine pass |
| CHESS-BL-009 | Profile a modern month for clock comments | Analysis | Proposed | P1 | Early 2013 data has no clock comments |
| CHESS-BL-010 | Build raw game sample capture | Data warehouse | Done | P1 | First 10 decompressed PGN blocks captured in `raw_game_sample` |
| CHESS-BL-011 | Build ingestion manifest design | Data warehouse | Done | P1 | Manifest written per run with lineage, counts, validation status, and output paths |
| CHESS-BL-012 | Build Bronze game ingestion prototype | Data warehouse | Done | P1 | Game-grain Bronze parser implemented and validated for `2013-01` |
| CHESS-BL-013 | Build Bronze validation checks | Data warehouse | Done | P1 | Row validation plus explicit Parquet schema validation implemented for v1 |
| CHESS-BL-014 | Define player dimension strategy | Semantic modeling | Proposed | P2 | Needed for player behavior and sandbagging analysis |
| CHESS-BL-015 | Define player rating event model | Semantic modeling | Proposed | Research | Needed for rating-growth/sandbagging research |
| CHESS-BL-016 | Define Power BI semantic model plan | Power BI | Proposed | P2 | Measures, relationships, display folders, visual conventions |
| CHESS-BL-017 | Define local warehouse physical design | Data warehouse | Done | P1 | Portable Parquet-backed medallion layers locally; DuckDB as query engine |
| CHESS-BL-018 | Plan Fabric migration path | Fabric | Proposed | P2 | Later move from on-prem/laptop prototype to Fabric |
| CHESS-BL-019 | Explore Synoptic Panel chess board visual | Power BI | Proposed | P2 | Later visual idea: use Synoptic Panel or a similar custom visual to make board-state analysis distinctive |
| CHESS-BL-020 | Define Silver game transformation guide | Data warehouse | Done | P1 | Silver game transformation implemented and validated for `2013-01` |
| CHESS-BL-021 | Build Gold game star schema transform | Data warehouse | Done | P1 | Gold `fact_game` and starter dimensions implemented and validated for `2013-01` |
| CHESS-BL-022 | Build DuckDB local warehouse load | Data warehouse | Done | P1 | Gold Parquet loaded into local DuckDB with FK validation |
| CHESS-BL-023 | Add Gold and DuckDB runbooks | Data warehouse | Done | P1 | Operational runbooks added under `docs/data-warehouse/` |

## Recently Completed

| ID | Item | Notes |
|---|---|---|
| CHESS-DONE-001 | Repo structure organized | Governance, planning, data warehouse, semantic modeling, Power BI, analysis, and source areas created |
| CHESS-DONE-002 | First month EDA completed | 2013-01 standard rated games profiled |
| CHESS-DONE-003 | Dual-grain decision documented | `fact_game` and `fact_move` |
| CHESS-DONE-004 | Opening dimension direction documented | ECO as parent classification; Lichess opening as observed variation label |
| CHESS-DONE-005 | Rating dimension direction documented | Separate White/Black rating dimensions; no average rating in v1 |
| CHESS-DONE-006 | Time-control dimension direction documented | Increment-based Lichess parsing and Bullet/Blitz/Rapid/Classical classification accepted |
| CHESS-DONE-007 | Bronze game ingestion guide drafted | Defines game-grain Bronze columns, manifest, validation checks, and first implementation path |
| CHESS-DONE-008 | Bronze game ingestion implemented | Local parser writes Bronze Parquet, raw game sample Parquet, and ingestion manifest |
| CHESS-DONE-009 | Bronze validation implemented | Row-level sanity checks and output Parquet schema checks pass for `2013-01` |
| CHESS-DONE-010 | Silver game transformation implemented | Local transform writes Silver game, time-control dimension, termination dimension, rating-difference bucket dimension, and manifest |
| CHESS-DONE-011 | Gold game star schema implemented | Local transform writes `fact_game`, date/rating/time-control/termination/rating-bucket/ECO/opening dimensions, and manifest |
| CHESS-DONE-012 | DuckDB warehouse load implemented | Local load creates `chess_analytics.duckdb` from Gold Parquet and validates fact-to-dimension relationships |

## Parking Lot

| Idea | Notes |
|---|---|
| Predict underrated/sandbagging players | Use first few games, opening choices, performance score, time control, and rating growth |
| Machine learning over positions | Requires careful storage strategy and likely engine/eval data |
| Endgame training recommendations | Identify common and poorly converted endgames |
| Time pressure error behavior | Requires modern data with clock comments and eval data |
| Chess board visual storytelling | Synoptic Panel could show board squares and position-related insights once move/position data exists |
