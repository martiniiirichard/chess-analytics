# Chess Analytics Project Plan

## Goal

Build a robust chess analytics platform that helps answer practical player-development questions from the Lichess open database, starting on-prem and leaving a clean path to Microsoft Fabric later.

## Context

The source is monthly PGN exports from Lichess. Standard rated games currently total billions of games, with each month published independently as `.pgn.zst`. The first standard month is 2013-01: 17.8 MB compressed, 121,332 games.

Lichess notes that PGN files contain headers, moves, comments, clock data for newer games, and Stockfish evaluations for a minority of standard rated games. Evaluation coverage is about 6% for standard rated games, so any mistake/blunder analysis must account for partial coverage.

## Decision Needed

For the pilot, use dual grain:

- `fact_game`: one row per game.
- `fact_move`: one row per half-move/ply.

This is the strongest modeling line because game-grain analysis remains cheap while move-grain analysis keeps the nuance needed for phase, mistake, clock, conversion, and endgame work.

## Output Format

The first milestone should produce:

- A short project charter.
- A data profiling report from 2013-01.
- A source-to-target draft for `fact_game`.
- A later source-to-target draft for `fact_move` after the game-grain contract is stable.
- A first-pass metric dictionary.
- A small Power BI-ready analytical extract, likely Parquet or SQL tables.

## Constraints

- Do not design around full-scale volume until the pilot proves the analytics are useful.
- Do not treat `mistake` as a universal source column. It is a derived metric based on evaluations, and evals are sparse.
- Do not rely on GUI chess databases for large PGN handling. Use programmatic parsing.
- Keep raw files immutable and separated from parsed outputs.
- Keep data files out of Git.

## Done When

Phase 1 is done when we can explain:

- What fields exist in the raw PGN.
- How many games and moves parse cleanly.
- Which analysis questions are answerable immediately.
- Which questions require engine evaluations, additional datasets, or deeper classification logic.
- Whether move-grain storage is viable for a realistic next slice.

## Phase Plan

| Phase | Name | Outcome |
|---|---|---|
| 0 | Project framing | Charter, repo structure, first source selected |
| 1 | First-month EDA | Parse 2013-01 and profile game/move fields |
| 2 | Metric contract v1 | Define score, time-control class, opening family, phase, endgame start |
| 3 | Local warehouse prototype | Load game and move facts into local SQL/warehouse tables |
| 4 | Power BI prototype | Build first report pages over curated facts |
| 5 | Scale test | Run a larger modern month and measure cost/performance |
| 6 | Fabric migration plan | Map landing/bronze/silver/gold and semantic model to Fabric |

## Initial Backlog

Detailed backlog and parking-lot items live in `docs/planning/backlog.md`.

| ID | Work Item | Acceptance Criteria |
|---|---|---|
| CHESS-001 | Create project charter | Goal, scope, constraints, success criteria are documented |
| CHESS-002 | Download 2013-01 source | Raw `.pgn.zst` is stored in local landing path with source URL recorded |
| CHESS-003 | Confirm parser stack | Python can read zstd stream and parse PGN games programmatically |
| CHESS-004 | Profile game headers | Counts and null rates for headers like Result, ECO, Opening, TimeControl, Elo, Termination |
| CHESS-005 | Profile moves | Move counts, parse failures, legal move reconstruction, comments/evals availability |
| CHESS-006 | Draft game fact source-to-target | One-row-per-game source fields, transformations, candidate dimensions, and validation candidates documented |
| CHESS-007 | Draft move fact source-to-target | One-row-per-ply target columns and keys documented after game-grain mapping is reviewed |
| CHESS-008 | Define time-control classes | Bullet/blitz/rapid/classical/correspondence rules documented and tested |
| CHESS-009 | Define phase/endgame v1 | Rules-based opening/middlegame/endgame classification drafted |
| CHESS-010 | Produce EDA readout | Findings, risks, and next strongest move summarized for stakeholder-style update |

## Stakeholder Status Template

Use this format for boss/boss's boss updates:

```text
Goal:
Current State:
Progress Since Last Update:
Key Finding:
Decision/Risk:
Next Milestone:
Ask:
```

