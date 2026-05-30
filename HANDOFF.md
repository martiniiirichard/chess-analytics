# Chess Analytics - Handoff State

> Update this file at every natural stopping point. Paste it into a new session to resume without context loss.

---

## Current State

**Branch:** `main` - up to date with origin
**Last pushed commit:** check with `git log -1 --oneline`
**Processed months:** `2013-01`, `2013-02`, and `2013-03` (403,928 total games)

### Pipeline Status

| Layer | Script | Status | Output |
|---|---|---|---|
| Bronze | `src/data_warehouse/ingestion/ingest_bronze_game.py` | Done + committed | `data/bronze/game/source_month=YYYY-MM/bronze_game.parquet` |
| Silver | `src/data_warehouse/transforms/build_silver_game.py` | Done + committed | `data/silver/game/source_month=YYYY-MM/silver_game.parquet` |
| Gold | `src/data_warehouse/transforms/build_gold_game.py` | Done + committed | `data/gold/game/source_month=YYYY-MM/fact_game.parquet` |
| DuckDB Load | `src/data_warehouse/load/load_duckdb.py` | Done + committed | `data/warehouse/chess_analytics.duckdb` (gitignored) |
| Monthly Orchestration | `src/data_warehouse/orchestration/process_month.py` | Done locally | `data/orchestration/source_month=YYYY-MM/monthly_process_manifest.json` |
| Power BI PBIP | `powerbi/reports/LiChess Analysis/LiChess Analysis.pbip` | Local prototype | Thick PBIP connected to Gold Parquet via TMDL |

### Gold Outputs

Gold fact output:

```text
data/gold/game/source_month=YYYY-MM/fact_game.parquet
```

Gold dimensions are stored in:

```text
data/gold/dimensions/
```

| File | Rows | Notes |
|---|---:|---|
| `fact_game.parquet` | 403,928 | Loaded in DuckDB across three fact partitions |
| `dim_date.parquet` | 91 | Year/month/quarter/DOW |
| `dim_white_rating.parquet` | 1,528 | PK = `WhiteRating_SK` |
| `dim_black_rating.parquet` | 1,540 | PK = `BlackRating_SK` |
| `dim_time_control.parquet` | 521 | Rebuilt globally from all Silver partitions |
| `dim_termination.parquet` | 2 | Promoted from Silver |
| `dim_rating_difference_bucket.parquet` | 7 | Promoted from Silver |
| `dim_eco.parquet` | 456 | ECO categories A-E |
| `dim_opening_variation.parquet` | 2,257 | FK to dim_eco |

---

## Key Architecture Decisions

- **Storage:** Parquet (zstd). DuckDB is the query engine over Parquet, not a separate system of record.
- **Power BI source path:** The local PBIP semantic model reads Gold Parquet directly. DuckDB ODBC was not available locally, and Parquet is the portable path for Fabric/Databricks later.
- **Surrogate keys:** SHA-256 63-bit stable keys. Unknown/sentinel members use `SK = 0`.
- **Unknown rating sentinel:** `100` (not null). Anonymous `"?"` players in Bronze map to Elo = 100 in Silver/Gold.
- **Rating dims:** Two separate tables (`dim_white_rating`, `dim_black_rating`) so both Power BI relationships stay active. PK column name matches FK name in `fact_game` for auto-detection.
- **Rating bands:** 200-point intervals; below 800 grouped as `Under 800`; 2200+ open-ended.
- **Opening model:** `dim_eco -> dim_opening_variation -> fact_game`.
- **Player dimension:** Deferred. `"?"` player names pass through Silver/Gold untouched; Gold will need a `dim_player` with Unknown member (`SK = 0`) when built.
- **Move-grain fact:** Deferred until game-grain warehouse is stable.
- **FEN / engine evals / ML:** Deferred.

---

## Run Commands

```powershell
# Activate venv from project root.
.venv\Scripts\activate

# Standard local monthly workflow:
# 1. Download raw file with PowerShell Invoke-WebRequest.
# 2. Run Python orchestration after the raw file exists.
python src/data_warehouse/orchestration/process_month.py --source-month YYYY-MM --output-root data
```

---

## Next Steps

1. Open `powerbi/reports/LiChess Analysis/LiChess Analysis.pbip` in Power BI Desktop and refresh the semantic model.
2. Compare Power BI `Game Count` to the Gold/DuckDB validated count of `403,928` games for processed months.
3. Confirm relationships in Model view and run a first visual smoke test by time control, ECO, score %, and rating bands.
4. If Power BI refresh succeeds, decide whether to keep scaling months or start report-page design.
5. Build `dim_player` when player analytics are needed; pre-seed Unknown member (`SK = 0`).
6. Define move-grain source-to-target only after game-grain reporting proves useful.

---

## Open Decisions

- **DuckDB persistence:** Query-only over Parquet vs persisted DuckDB database. Current local implementation creates a persisted DuckDB database for convenience while preserving Parquet as the portable warehouse storage.
- **Multi-month strategy:** Keep separate `source_month=` fact partition files. Gold dimensions rebuild globally from all available Silver game partitions during the local prototype.

---

## Gotchas / Non-Obvious Decisions

- Silver `TRANSFORM_VERSION = "silver-game-0.2.0"` normalizes null ratings to sentinel `100` and recomputes `AbsRatingDifference` and `RatingDifferenceBucket_SK` in Silver.
- Pre-refactor reference copy of Silver lives at `src/data_warehouse/transforms/_archive/build_silver_game_v0.2.0.py`.
- Bronze manifest is at `data/bronze/manifests/source_month=2013-01/ingestion_manifest.json`, not co-located with the Parquet.
- The `"?"` player names (90 White, 168 Black in the pilot month) are not cleaned in Silver or Gold. They remain as-is until `dim_player` is built.
- Python network download can be sandbox-blocked. The official local workflow is PowerShell `Invoke-WebRequest` first, then `process_month.py`; it will skip download when the raw file exists.
- The PBIP uses absolute local paths in Power Query M because this is a local Desktop prototype. Fabric/Databricks migration will require replacing these with workspace/lakehouse-backed sources.
- Power BI model work should prefer the Power BI MCP server, `pbir-cli`, semantic-model skills, PBIP skills, and TMDL skills before raw file edits when those tools are available.
- Power BI visual/report design work should use relevant report design, visual review, PBIR format, Deneb, SVG, Python/R visual, and theme skills before editing report pages.
