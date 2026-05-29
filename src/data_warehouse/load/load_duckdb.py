from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb


# ------------------------------------------------------------------------------
# CONSTANTS
# ------------------------------------------------------------------------------

LOAD_VERSION = "duckdb-load-0.1.0"
DB_FILENAME = "chess_analytics.duckdb"

DIMENSION_TABLES = [
    "dim_date",
    "dim_white_rating",
    "dim_black_rating",
    "dim_time_control",
    "dim_termination",
    "dim_rating_difference_bucket",
    "dim_eco",
    "dim_opening_variation",
]


# ------------------------------------------------------------------------------
# LOAD — FACT_GAME
# fact_game is partitioned by source_month; glob picks up all loaded months.
# ------------------------------------------------------------------------------

def load_fact_game(conn: duckdb.DuckDBPyConnection, gold_root: Path) -> int:
    pattern = (gold_root / "game" / "source_month=*" / "fact_game.parquet").as_posix()
    conn.execute(f"""
        CREATE OR REPLACE TABLE fact_game AS
        SELECT * FROM read_parquet('{pattern}', hive_partitioning = false)
    """)
    return conn.execute("SELECT COUNT(*) FROM fact_game").fetchone()[0]


# ------------------------------------------------------------------------------
# LOAD — DIMENSIONS
# Dimensions are single files; CREATE OR REPLACE replaces on each run.
# ------------------------------------------------------------------------------

def load_dimension(conn: duckdb.DuckDBPyConnection, table_name: str, parquet_path: Path) -> int:
    path = parquet_path.as_posix()
    conn.execute(f"""
        CREATE OR REPLACE TABLE {table_name} AS
        SELECT * FROM read_parquet('{path}')
    """)
    return conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def load_all_dimensions(
    conn: duckdb.DuckDBPyConnection, dim_root: Path
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in DIMENSION_TABLES:
        parquet_path = dim_root / f"{table_name}.parquet"
        if not parquet_path.exists():
            raise FileNotFoundError(f"Dimension Parquet not found: {parquet_path}")
        counts[table_name] = load_dimension(conn, table_name, parquet_path)
    return counts


# ------------------------------------------------------------------------------
# VALIDATION
# ------------------------------------------------------------------------------

def validate_load(
    conn: duckdb.DuckDBPyConnection,
    row_counts: dict[str, int],
    gold_manifest_path: Path | None,
    source_month: str,
) -> tuple[str, list[str]]:
    messages: list[str] = []
    status = "pass"

    # -- Row count sanity -----------------------------------------------------
    for table, count in row_counts.items():
        if count == 0:
            status = "fail"
            messages.append(f"{table} loaded 0 rows.")

    # -- FK spot-checks -------------------------------------------------------
    fk_checks = [
        ("fact_game", "Date_SK",                   "dim_date",                    "Date_SK"),
        ("fact_game", "WhiteRating_SK",             "dim_white_rating",            "WhiteRating_SK"),
        ("fact_game", "BlackRating_SK",             "dim_black_rating",            "BlackRating_SK"),
        ("fact_game", "TimeControl_SK",             "dim_time_control",            "TimeControl_SK"),
        ("fact_game", "Termination_SK",             "dim_termination",             "Termination_SK"),
        ("fact_game", "RatingDifferenceBucket_SK",  "dim_rating_difference_bucket","RatingDifferenceBucket_SK"),
        ("fact_game", "ECO_SK",                     "dim_eco",                     "ECO_SK"),
        ("fact_game", "OpeningVariation_SK",        "dim_opening_variation",       "OpeningVariation_SK"),
    ]
    for fact_table, fact_col, dim_table, dim_col in fk_checks:
        orphan_count = conn.execute(f"""
            SELECT COUNT(*) FROM {fact_table} f
            WHERE f.{fact_col} NOT IN (SELECT {dim_col} FROM {dim_table})
        """).fetchone()[0]
        if orphan_count > 0:
            status = "fail"
            messages.append(
                f"{orphan_count} fact_game rows have no match in {dim_table}.{dim_col}."
            )

    # -- Gold manifest cross-check --------------------------------------------
    if gold_manifest_path and gold_manifest_path.exists():
        manifest = json.loads(gold_manifest_path.read_text(encoding="utf-8"))
        expected = manifest.get("QualityCounts", {}).get("FactRowsWritten")
        actual = row_counts.get("fact_game", 0)
        if expected is not None and actual != expected:
            status = "fail"
            messages.append(
                f"fact_game has {actual} rows in DuckDB but Gold manifest reports {expected}."
            )

    if status == "pass":
        messages.append("All DuckDB load validation checks passed.")
    return status, messages


# ------------------------------------------------------------------------------
# ORCHESTRATION
# ------------------------------------------------------------------------------

def load(args: argparse.Namespace) -> dict[str, Any]:
    output_root = args.output_root.resolve()
    gold_root = output_root / "gold"
    dim_root = gold_root / "dimensions"
    db_path = (
        Path(args.db_path).resolve()
        if args.db_path
        else output_root / "warehouse" / DB_FILENAME
    )
    gold_manifest_path = (
        gold_root / "manifests" / f"source_month={args.source_month}" / "gold_game_manifest.json"
    )

    db_path.parent.mkdir(parents=True, exist_ok=True)

    load_run_id = args.load_run_id or str(uuid.uuid4())
    started_at_utc = datetime.now(UTC).isoformat()

    conn = duckdb.connect(str(db_path))
    try:
        fact_count = load_fact_game(conn, gold_root)
        dim_counts = load_all_dimensions(conn, dim_root)
    finally:
        conn.close()

    row_counts = {"fact_game": fact_count, **dim_counts}

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        validation_status, validation_messages = validate_load(
            conn, row_counts, gold_manifest_path, args.source_month
        )
    finally:
        conn.close()

    manifest = {
        "LoadRunID": load_run_id,
        "SourceMonth": args.source_month,
        "DBPath": str(db_path),
        "StartedAtUTC": started_at_utc,
        "CompletedAtUTC": datetime.now(UTC).isoformat(),
        "LoadVersion": LOAD_VERSION,
        "TableRowCounts": row_counts,
        "ValidationStatus": validation_status,
        "ValidationMessages": validation_messages,
    }

    manifest_path = output_root / "warehouse" / "load_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load Gold Parquet files into a persistent DuckDB warehouse."
    )
    parser.add_argument("--source-month", required=True)
    parser.add_argument("--output-root", default=Path("data"), type=Path)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--load-run-id", default=None)
    args = parser.parse_args()

    manifest = load(args)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
