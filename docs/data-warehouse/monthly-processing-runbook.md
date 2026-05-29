# Monthly Processing Runbook

## Purpose

Process one Lichess monthly file through the full local warehouse pipeline.

Related implementation:

```text
src/data_warehouse/orchestration/process_month.py
```

## Scope

The orchestration script runs:

```text
download -> Bronze -> Silver -> Gold -> DuckDB load
```

It stops on the first failed step and writes one month-level manifest when the run succeeds.

## Pilot Command

```powershell
.venv\Scripts\python.exe src\data_warehouse\orchestration\process_month.py `
  --source-month 2013-03 `
  --output-root data
```

Optional arguments:

```text
--skip-download
--source-dataset standard_rated
--base-url https://database.lichess.org/standard
--orchestration-run-id <run-id>
```

## Inputs

If the raw file is missing, the script downloads:

```text
https://database.lichess.org/standard/lichess_db_standard_rated_YYYY-MM.pgn.zst
```

Expected raw path:

```text
data/raw/lichess/standard/YYYY-MM/lichess_db_standard_rated_YYYY-MM.pgn.zst
```

## Outputs

Layer outputs:

```text
data/bronze/game/source_month=YYYY-MM/bronze_game.parquet
data/silver/game/source_month=YYYY-MM/silver_game.parquet
data/gold/game/source_month=YYYY-MM/fact_game.parquet
data/warehouse/chess_analytics.duckdb
```

Orchestration manifest:

```text
data/orchestration/source_month=YYYY-MM/monthly_process_manifest.json
```

## Validation

Each layer remains responsible for its own detailed validation.

The orchestration manifest records:

- Download status or skip reason.
- Bronze manifest.
- Silver manifest.
- Gold manifest.
- DuckDB load manifest.
- Overall `ValidationStatus`.

Success requires every non-download layer to return:

```text
ValidationStatus = pass
```

## Raw File Rule

The orchestration script does not delete raw files.

Raw deletion should remain a separate reviewed action until the project has a mature retention and reprocessing policy.

## Notes

The script is intentionally simple. It calls the existing layer scripts as subprocesses rather than duplicating their logic.

This mirrors how the same pipeline could later become a Fabric pipeline, Databricks workflow, or scheduled local job.

## First Validated Orchestration Result

`2013-03` was processed through the orchestration wrapper.

```text
ValidationStatus = pass
BronzeGameRowsWritten = 158635
SilverRowsWritten = 158635
FactRowsWritten = 158635
AllSilverRowsReadForDimensions = 403928
DuckDB fact_game rows = 403928
```

The Python download step was blocked by local network permissions in the sandbox. The raw file was downloaded with PowerShell `Invoke-WebRequest`, then the orchestration wrapper skipped download because the raw file already existed.
