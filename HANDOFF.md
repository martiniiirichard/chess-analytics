# Chess Analytics — Handoff State

> Update this file at every natural stopping point. Paste it into a new session to resume without context loss.

---

## Current State

**Branch:** `main` — up to date with origin  
**Last commit:** `5ea1884` — Implement Gold game star schema transform  
**Pilot month:** `2013-01` (121,332 games)

### Pipeline Status

| Layer | Script | Status | Output |
|---|---|---|---|
| Bronze | `src/data_warehouse/ingestion/ingest_bronze_game.py` | ✅ Done + committed | `data/bronze/game/source_month=2013-01/bronze_game.parquet` |
| Silver | `src/data_warehouse/transforms/build_silver_game.py` | ✅ Done + committed | `data/silver/game/source_month=2013-01/silver_game.parquet` |
| Gold | `src/data_warehouse/transforms/build_gold_game.py` | ✅ Done + committed | `data/gold/game/source_month=2013-01/fact_game.parquet` |

### Gold Outputs (all in `data/gold/dimensions/`)

| File | Rows | Notes |
|---|---|---|
| `fact_game.parquet` | 121,332 | 8 FK columns, full lineage |
| `dim_date.parquet` | 32 | Year/month/quarter/DOW |
| `dim_white_rating.parquet` | 1,346 | PK = `WhiteRating_SK` |
| `dim_black_rating.parquet` | 1,358 | PK = `BlackRating_SK` |
| `dim_time_control.parquet` | 396 | Promoted from Silver |
| `dim_termination.parquet` | 2 | Promoted from Silver |
| `dim_rating_difference_bucket.parquet` | 7 | Promoted from Silver |
| `dim_eco.parquet` | 412 | ECO categories A–E |
| `dim_opening_variation.parquet` | 1,847 | FK to dim_eco |

---

## Key Architecture Decisions

- **Storage:** Parquet (zstd). DuckDB is the query engine *over* Parquet — not a separate store.
- **Surrogate keys:** SHA-256 63-bit stable keys. Unknown/sentinel members use `SK = 0`.
- **Unknown rating sentinel:** `100` (not null). Anonymous `"?"` players in Bronze map to Elo = 100 in Silver/Gold.
- **Rating dims:** Two separate tables (`dim_white_rating`, `dim_black_rating`) so both Power BI relationships stay active. PK column name matches FK name in `fact_game` for auto-detection.
- **Rating bands:** 200-point intervals; below 800 grouped as "Under 800"; 2200+ open-ended.
- **Opening model:** `dim_eco → dim_opening_variation → fact_game`.
- **Player dimension:** Deferred. `"?"` player names pass through Silver/Gold untouched; Gold will need a `dim_player` with Unknown member (SK=0) when built.
- **Move-grain fact:** Deferred until game-grain warehouse is stable.
- **FEN / engine evals / ML:** All deferred.

---

## Run Commands

```powershell
# Activate venv (from project root)
.venv\Scripts\activate

# Bronze
python src/data_warehouse/ingestion/ingest_bronze_game.py --source-month 2013-01 --output-root data

# Silver
python src/data_warehouse/transforms/build_silver_game.py --source-month 2013-01 --output-root data

# Gold
python src/data_warehouse/transforms/build_gold_game.py --source-month 2013-01 --output-root data
```

---

## Next Steps (in order)

1. **DuckDB query layer** — add `src/data_warehouse/query/query_gold.py` (or similar) that opens DuckDB over the Gold Parquet files and exposes the star schema for ad-hoc SQL.
2. **Backlog update** — mark Gold game transform as done in `docs/planning/backlog.md`.
3. **Runbook** — write `docs/data-warehouse/gold/gold-game-transform-runbook.md`.
4. **Additional months** — run pipeline for more Lichess months to grow the dataset.
5. **Power BI connection** — connect Gold Parquet files to a Power BI semantic model.
6. **dim_player** — build when player analytics are needed; Unknown member (SK=0) pre-seeded.

---

## Open Decisions

- **DuckDB persistence:** Query-only (no `.duckdb` file as store) vs. persisted DuckDB database. Currently plan is query-only for Fabric portability — revisit when doing Power BI work.
- **Multi-month strategy:** Append new months to existing Parquet, or separate partition files per month? Currently partitioned by `source_month=` folder.

---

## Gotchas / Non-Obvious Decisions

- Silver `TRANSFORM_VERSION = "silver-game-0.2.0"` — v0.1.0 had null ratings passed through from Bronze. v0.2.0 normalises nulls to sentinel 100 and recomputes `AbsRatingDifference` and `RatingDifferenceBucket_SK` in Silver.
- Pre-refactor reference copy of Silver at `src/data_warehouse/transforms/_archive/build_silver_game_v0.2.0.py`.
- Bronze manifest is at `data/bronze/manifests/source_month=2013-01/ingestion_manifest.json` (not co-located with the Parquet).
- The `"?"` player names (90 White, 168 Black) are NOT cleaned in Silver or Gold — they remain as-is until `dim_player` is built.
