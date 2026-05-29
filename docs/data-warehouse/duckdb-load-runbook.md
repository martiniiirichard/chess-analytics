# DuckDB Load Runbook

## Purpose

Load Gold Parquet outputs into a local DuckDB database for SQL validation and Power BI exploration.

Related implementation:

```text
src/data_warehouse/load/load_duckdb.py
```

## Design Note

Parquet remains the portable warehouse storage.

DuckDB is a local query and exploration layer over the Gold outputs. The persisted `.duckdb` file is useful for local tooling, but it should not become the system of record.

## Inputs

- Gold `fact_game` Parquet partition(s).
- Gold dimension Parquet files.
- Python environment with `duckdb` installed.

## Pilot Command

```powershell
.venv\Scripts\python.exe src\data_warehouse\load\load_duckdb.py `
  --source-month 2013-01 `
  --output-root data
```

Optional output override:

```powershell
--db-path data\warehouse\chess_analytics.duckdb
```

## Outputs

```text
data/warehouse/chess_analytics.duckdb
data/warehouse/load_manifest.json
```

The `.duckdb` database is gitignored.

## Loaded Tables

```text
fact_game
dim_date
dim_white_rating
dim_black_rating
dim_time_control
dim_termination
dim_rating_difference_bucket
dim_eco
dim_opening_variation
```

## Load Behavior

- `fact_game` is loaded from all `data/gold/game/source_month=*/fact_game.parquet` partitions.
- Dimensions are loaded from single files in `data/gold/dimensions/`.
- Tables are created with `CREATE OR REPLACE`, so each run refreshes the local DuckDB tables.

## Validation

Validation checks:

- Each loaded table has more than zero rows.
- `fact_game` row count matches the Gold manifest when available.
- Fact foreign keys map to the loaded dimension keys.

## First Validated Pilot Result

```text
ValidationStatus = pass
fact_game = 121332
dim_date = 32
dim_white_rating = 1346
dim_black_rating = 1358
dim_time_control = 396
dim_termination = 2
dim_rating_difference_bucket = 7
dim_eco = 412
dim_opening_variation = 1847
```

## Output Size From Pilot

```text
chess_analytics.duckdb = 8663040 bytes
```

## Notes

This local database is useful for quick SQL checks, ad hoc profiling, and early Power BI connectivity tests.

For Fabric or Databricks migration, use the Parquet Gold outputs as the portable source.
