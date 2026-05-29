# Multi-Month Processing Strategy

## Purpose

Define how the local warehouse should process more than one Lichess monthly file without breaking fact partitions, dimension keys, validation, or cloud portability.

## Current Decision

Use month-partitioned fact outputs and globally rebuilt dimensions during the local prototype.

This keeps the process simple while the dimensional model is still changing.

## Fact Strategy

Large fact-like outputs stay partitioned by `source_month`.

Current partitioned outputs:

```text
data/bronze/game/source_month=YYYY-MM/bronze_game.parquet
data/silver/game/source_month=YYYY-MM/silver_game.parquet
data/gold/game/source_month=YYYY-MM/fact_game.parquet
```

Rules:

- One file per processed month per layer during the prototype.
- Rerunning a month overwrites that month's partition output.
- No append-in-place behavior for fact partitions until orchestration is formalized.

## Dimension Strategy

Small dimensions are rebuilt globally from all processed months for now.

Current single-file Gold dimensions:

```text
data/gold/dimensions/dim_date.parquet
data/gold/dimensions/dim_white_rating.parquet
data/gold/dimensions/dim_black_rating.parquet
data/gold/dimensions/dim_time_control.parquet
data/gold/dimensions/dim_termination.parquet
data/gold/dimensions/dim_rating_difference_bucket.parquet
data/gold/dimensions/dim_eco.parquet
data/gold/dimensions/dim_opening_variation.parquet
```

Rationale:

- Rebuild is easier to validate than incremental dimension merge logic.
- Deterministic hash keys keep dimension keys stable across rebuilds.
- Dimension sizes are small enough that global rebuild is cheap in the prototype.

Implementation note:

- Gold now reads all available Silver game partitions when rebuilding global dimensions.
- `fact_game` is still written only for the requested `source_month`.
- This keeps fact processing partitioned while keeping dimensions valid across all processed months.

## DuckDB Strategy

DuckDB loads all Gold fact partitions:

```text
data/gold/game/source_month=*/fact_game.parquet
```

Dimensions are loaded from the current Gold dimension files.

DuckDB remains a local query layer. Parquet remains the portable warehouse storage.

## Validation Strategy

For each new month:

1. Bronze validation must pass.
2. Silver validation must pass.
3. Gold validation must pass.
4. DuckDB load validation must pass.
5. Total DuckDB `fact_game` rows should equal the sum of processed Gold fact partitions.

Track these counts in manifests:

```text
data/bronze/manifests/source_month=YYYY-MM/ingestion_manifest.json
data/silver/manifests/source_month=YYYY-MM/silver_game_manifest.json
data/gold/manifests/source_month=YYYY-MM/gold_game_manifest.json
data/warehouse/load_manifest.json
```

## Raw File Lifecycle

The raw `.pgn.zst` file can be deleted only after:

- Bronze raw sample was captured.
- Bronze, Silver, Gold, and DuckDB validations passed.
- Required manifests exist.
- No required processing step was skipped.

If any step fails, retain the raw file until the failure is understood.

## Second-Month Pilot

Use `2013-02` as the next pilot month.

Goal:

```text
download -> Bronze -> Silver -> Gold -> DuckDB load -> validation
```

Success criteria:

- `2013-02` produces valid Bronze/Silver/Gold outputs.
- DuckDB `fact_game` row count includes both `2013-01` and `2013-02`.
- No fact rows fail dimension relationship validation.

Validated result:

```text
2013-01 fact rows = 121332
2013-02 fact rows = 123961
DuckDB fact_game rows = 245293
DuckDB validation status = pass
```

## Open Decisions

- Whether to create a single orchestration script for month processing.
- Whether processed month inventory should be stored as a manifest table.
- Whether raw files should be deleted automatically or through a separate cleanup command.
