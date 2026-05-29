# Local Warehouse Physical Design

## Purpose

Define the local warehouse prototype so it can move cleanly to Microsoft Fabric or Databricks later.

This project should use portable lakehouse files as the durable warehouse storage. Local SQL tools are query engines over those files, not the system of record.

## Design Decision

Use a local medallion-style analytical warehouse:

```text
data/bronze -> data/silver -> data/gold
```

Primary storage format:

```text
Parquet, partitioned by source month where useful
```

Local query engine:

```text
DuckDB
```

Future cloud targets:

```text
Microsoft Fabric Lakehouse
Databricks Delta Lake
Power BI semantic model
```

## Rationale

Parquet-backed medallion layers keep the warehouse copyable to Fabric and Databricks.

SQL Server or SSMS may be useful for inspection or T-SQL practice, but SQL Server should not be the durable storage target for this prototype. A SQL Server-first design would create avoidable migration work when moving to lakehouse platforms.

DuckDB is preferred locally because it can query Parquet directly, supports SQL-based validation, and does not force the project into a database-specific storage format.

## Physical Layout

Recommended local folders:

```text
data/
  raw/
    lichess/
      standard/
        YYYY-MM/
          lichess_db_standard_rated_YYYY-MM.pgn.zst
  bronze/
    game/
      source_month=YYYY-MM/
        bronze_game.parquet
    manifests/
      source_month=YYYY-MM/
        ingestion_manifest.json
  silver/
    game/
      source_month=YYYY-MM/
        silver_game.parquet
    dimensions/
      dim_time_control.parquet
      dim_termination.parquet
      dim_rating_difference_bucket.parquet
      dim_white_rating.parquet
      dim_black_rating.parquet
  gold/
    fact_game/
      source_month=YYYY-MM/
        fact_game.parquet
    dimensions/
      dim_date.parquet
      dim_time_control.parquet
      dim_termination.parquet
      dim_rating_difference_bucket.parquet
      dim_white_rating.parquet
      dim_black_rating.parquet
      dim_eco.parquet
      dim_opening_variation.parquet
  samples/
    raw_game_sample/
      source_month=YYYY-MM/
        raw_game_sample.parquet
```

## Layer Responsibilities

| Layer | Responsibility | Storage Rule |
|---|---|---|
| Bronze | Preserve source-shaped data and lineage cheaply | Append or overwrite by `source_month` during pilot |
| Silver | Type, parse, validate, conform, and quarantine | Materialize clean tables with explicit schemas |
| Gold | Produce semantic-model-ready star schema | Keep facts narrow and dimensions descriptive |

## Local Query Pattern

DuckDB should query Parquet in place:

```sql
SELECT COUNT(*)
FROM read_parquet('data/bronze/game/source_month=2013-01/bronze_game.parquet');
```

For reusable local development, create DuckDB views over Parquet paths rather than duplicating data into a proprietary local database file.

## Cloud Portability

Fabric migration path:

```text
Parquet folders -> Fabric Lakehouse Files/Tables -> Direct Lake semantic model
```

Databricks migration path:

```text
Parquet folders -> Delta tables -> Databricks SQL / Power BI
```

When the schema stabilizes, evaluate writing Delta locally or converting Parquet to Delta in the cloud.

## Partitioning

Use `source_month=YYYY-MM` partition folders for large monthly facts.

Initial partitioned tables:

- `bronze_game`
- `silver_game`
- `fact_game`

Small dimensions should remain single Parquet outputs until size or maintenance requires partitioning.

## Compression

Use Parquet with `zstd` compression for local outputs.

Compression is handled by Parquet and should be sufficient for the v1 prototype. Do not introduce custom compressed intermediate formats unless profiling shows a clear storage or performance need.

## Validation

Each layer should write or reference validation evidence:

- Source row counts.
- Output row counts.
- Parse failure counts.
- Schema validation.
- Key uniqueness.
- Required relationship key coverage.
- Unknown/unmapped bucket counts.

## Open Decisions

- Whether DuckDB views should be generated from SQL files under `src/`.
- Whether Silver dimensions should be rebuilt globally from all months or incrementally merged.
- Whether Gold should be physically materialized before Power BI, or first modeled directly over Silver.
- When to introduce Delta Lake semantics.
