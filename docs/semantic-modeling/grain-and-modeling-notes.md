# Grain And Modeling Notes

## Business Processes

- Game played.
- Move made.
- Position evaluated, when evaluation data exists.
- Endgame entered, when our classification rules detect it.
- Error event occurred, when evaluation movement crosses a defined threshold.

## Candidate Facts

| Fact | Grain | Fact Type | Why It Exists |
|---|---|---|---|
| `fact_game` | One row per game | Transaction fact | Fast outcome, opening, rating, time-control, termination analysis |
| `fact_move` | One row per ply in a game | Transaction fact | Phase, move choice, time, material, and transition analysis |
| `fact_position_eval` | One row per evaluated position | Transaction fact | Mistake/blunder and conversion analysis where eval exists |
| `fact_endgame_transition` | One row per game/endgame entry | Accumulating/derived event fact | Endgame frequency and conversion analysis |
| `fact_opening_game_summary` | One row per opening/time-control/rating band/month | Aggregate fact | Power BI performance path for common opening questions |

## Recommended Pilot Grain

Build both `fact_game` and `fact_move`.

Reason: game-level metadata alone cannot answer the interesting chess questions, but move-level alone is too heavy for common BI queries. This is a classic dimensional modeling tradeoff: preserve detail where it creates analytical leverage, then add aggregates for common reporting paths.

## PGN Parsing Approach

PGN is semi-structured text:

- Headers are key/value tags like `[ECO "B30"]`.
- Moves are notation text with comments.
- Comments can include structured annotations such as `[%eval 0.17]` and `[%clk 0:00:30]`.

Use specialized packages instead of handwritten parsing:

- `python-chess`: read PGN, validate/replay moves, produce FEN/material/side-to-move.
- `zstandard`: stream `.zst` compressed files without fully decompressing first.
- `pandas` or `polars`: EDA tables.
- `pyarrow`: write Parquet for efficient local analytics.

## First-Pass Data Architecture

| Layer | Storage | Purpose |
|---|---|---|
| Transient Landing | Raw `.pgn.zst` monthly file | Temporary source capture during a controlled ingestion run |
| Ingestion Evidence | Manifest plus `raw_game_sample` | Durable traceability after raw monthly files are deleted |
| Bronze | Parsed game and move records | Minimal transformation, source-faithful |
| Silver | Cleaned/enriched facts | Time-control class, result normalization, move numbers, material state |
| Gold | BI-ready facts/dimensions/aggregates | Power BI and stakeholder-facing metrics |

Raw monthly files may be deleted after Bronze ingestion completes, validation passes, an ingestion manifest is written, and the raw game sample is captured. This keeps laptop storage manageable while preserving enough evidence to troubleshoot parser behavior.

## Open Modeling Questions

- Should bots be excluded by default?
- Should games under a minimum number of plies be excluded from opening/endgame analysis?
- Should we separate rated pool by time control before comparing opening results?
- Should `mistake` use Lichess eval comments only, the separate eval database, or our own engine pass later?
- Should endgame start be material-based, move-number-based, engine-based, or hybrid?

