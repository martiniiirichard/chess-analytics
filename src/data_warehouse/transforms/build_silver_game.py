from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

TRANSFORM_VERSION = "silver-game-0.2.0"
SCHEMA_VERSION = "silver-game-v1"
TIME_CONTROL_PATTERN = re.compile(r"^(?P<initial>\d+)\+(?P<increment>\d+)$")
UNKNOWN_RATING_SENTINEL = 100


# ──────────────────────────────────────────────────────────────────────────────
# SHARED HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def stable_positive_key(value: str) -> int:
    """Deterministic 63-bit key; stable across reruns."""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


def parse_game_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y.%m.%d").date()
    except ValueError:
        return None


def date_key(game_date: date | None) -> int | None:
    if game_date is None:
        return None
    return (game_date.year * 10000) + (game_date.month * 100) + game_date.day


# ──────────────────────────────────────────────────────────────────────────────
# DIM_TIME_CONTROL
# ──────────────────────────────────────────────────────────────────────────────

DIM_TIME_CONTROL_SCHEMA = pa.schema(
    [
        pa.field("TimeControl_SK", pa.int64()),
        pa.field("TimeControlRaw", pa.string()),
        pa.field("InitialSeconds", pa.int32()),
        pa.field("IncrementSeconds", pa.int32()),
        pa.field("EstimatedGameSeconds", pa.int32()),
        pa.field("TimeControlClass", pa.string()),
        pa.field("TimeControlType", pa.string()),
        pa.field("IsParsed", pa.int8()),
    ]
)


def classify_time_control(estimated_game_seconds: int | None) -> str:
    if estimated_game_seconds is None:
        return "Unknown"
    if estimated_game_seconds < 180:
        return "Bullet"
    if estimated_game_seconds < 480:
        return "Blitz"
    if estimated_game_seconds < 1500:
        return "Rapid"
    return "Classical"


def parse_time_control(raw_value: str | None) -> dict[str, Any]:
    """Parse Lichess increment notation; unparsed values map to the shared Unknown key (SK=0)."""
    raw_text = (raw_value or "").strip()
    match = TIME_CONTROL_PATTERN.match(raw_text)
    if not match:
        return {
            "TimeControl_SK": 0,
            "TimeControlRaw": raw_text or "Unknown",
            "InitialSeconds": None,
            "IncrementSeconds": None,
            "EstimatedGameSeconds": None,
            "TimeControlClass": "Unknown",
            "TimeControlType": "unknown",
            "IsParsed": 0,
        }
    initial_seconds = int(match.group("initial"))
    increment_seconds = int(match.group("increment"))
    estimated_game_seconds = initial_seconds + (40 * increment_seconds)
    return {
        "TimeControl_SK": stable_positive_key(f"time_control|{raw_text}"),
        "TimeControlRaw": raw_text,
        "InitialSeconds": initial_seconds,
        "IncrementSeconds": increment_seconds,
        "EstimatedGameSeconds": estimated_game_seconds,
        "TimeControlClass": classify_time_control(estimated_game_seconds),
        "TimeControlType": "increment",
        "IsParsed": 1,
    }


def build_dim_time_control(
    bronze_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse time control for every Bronze row.

    Returns (per_row_results, dim_rows).
    per_row_results[i] holds the parsed dict for bronze_rows[i]; used when
    building silver_game rows to avoid re-parsing.
    """
    per_row: list[dict[str, Any]] = []
    members: dict[int, dict[str, Any]] = {}
    for row in bronze_rows:
        parsed = parse_time_control(row.get("TimeControlRaw"))
        per_row.append(parsed)
        members[parsed["TimeControl_SK"]] = parsed
    dim_rows = sorted(members.values(), key=lambda r: (r["TimeControl_SK"], r["TimeControlRaw"]))
    return per_row, dim_rows


# ──────────────────────────────────────────────────────────────────────────────
# DIM_TERMINATION
# ──────────────────────────────────────────────────────────────────────────────

DIM_TERMINATION_SCHEMA = pa.schema(
    [
        pa.field("Termination_SK", pa.int64()),
        pa.field("TerminationRaw", pa.string()),
        pa.field("TerminationLabel", pa.string()),
        pa.field("IsTimeForfeit", pa.int8()),
        pa.field("MappingStatus", pa.string()),
    ]
)


def map_termination(raw_value: str | None) -> dict[str, Any]:
    raw_text = (raw_value or "").strip()
    if not raw_text:
        return {
            "Termination_SK": 0,
            "TerminationRaw": "Unknown",
            "TerminationLabel": "Unknown",
            "IsTimeForfeit": 0,
            "MappingStatus": "unknown",
        }
    is_time_forfeit = 1 if raw_text == "Time forfeit" else 0
    return {
        "Termination_SK": stable_positive_key(f"termination|{raw_text}"),
        "TerminationRaw": raw_text,
        "TerminationLabel": raw_text,
        "IsTimeForfeit": is_time_forfeit,
        "MappingStatus": "mapped",
    }


def build_dim_termination(
    bronze_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map termination for every Bronze row.

    Returns (per_row_results, dim_rows).
    """
    per_row: list[dict[str, Any]] = []
    members: dict[int, dict[str, Any]] = {}
    for row in bronze_rows:
        mapped = map_termination(row.get("TerminationRaw"))
        per_row.append(mapped)
        members[mapped["Termination_SK"]] = mapped
    dim_rows = sorted(members.values(), key=lambda r: (r["Termination_SK"], r["TerminationRaw"]))
    return per_row, dim_rows


# ──────────────────────────────────────────────────────────────────────────────
# DIM_RATING_DIFFERENCE_BUCKET
# ──────────────────────────────────────────────────────────────────────────────

DIM_RATING_DIFFERENCE_BUCKET_SCHEMA = pa.schema(
    [
        pa.field("RatingDifferenceBucket_SK", pa.int8()),
        pa.field("RatingDifferenceBucketLabel", pa.string()),
        pa.field("MinDifference", pa.int16()),
        pa.field("MaxDifference", pa.int16()),
        pa.field("SortOrder", pa.int8()),
    ]
)


def normalize_rating(value: int | None) -> int:
    """Null ratings (anonymous players) map to UNKNOWN_RATING_SENTINEL (100)."""
    if value is None:
        return UNKNOWN_RATING_SENTINEL
    return value


def assign_rating_difference_bucket(abs_diff: int) -> int:
    """Return the RatingDifferenceBucket_SK for a given absolute rating difference."""
    if abs_diff < 50:
        return 1
    if abs_diff < 100:
        return 2
    if abs_diff < 200:
        return 3
    if abs_diff < 400:
        return 4
    if abs_diff < 600:
        return 5
    return 6


def build_dim_rating_difference_bucket() -> list[dict[str, Any]]:
    """Return the static rating difference bucket dimension rows.

    SK=0 (Unknown) is seeded for future use; fact_game rows will not reference
    it after rating normalization guarantees no null diffs.
    """
    return [
        {"RatingDifferenceBucket_SK": 0, "RatingDifferenceBucketLabel": "Unknown",             "MinDifference": None, "MaxDifference": None, "SortOrder": 0},
        {"RatingDifferenceBucket_SK": 1, "RatingDifferenceBucketLabel": "0-49 roughly equal",  "MinDifference": 0,    "MaxDifference": 49,   "SortOrder": 1},
        {"RatingDifferenceBucket_SK": 2, "RatingDifferenceBucketLabel": "50-99 small edge",    "MinDifference": 50,   "MaxDifference": 99,   "SortOrder": 2},
        {"RatingDifferenceBucket_SK": 3, "RatingDifferenceBucketLabel": "100-199 meaningful edge", "MinDifference": 100, "MaxDifference": 199, "SortOrder": 3},
        {"RatingDifferenceBucket_SK": 4, "RatingDifferenceBucketLabel": "200-399 large edge",  "MinDifference": 200,  "MaxDifference": 399,  "SortOrder": 4},
        {"RatingDifferenceBucket_SK": 5, "RatingDifferenceBucketLabel": "400-599 very large edge", "MinDifference": 400, "MaxDifference": 599, "SortOrder": 5},
        {"RatingDifferenceBucket_SK": 6, "RatingDifferenceBucketLabel": "600+ extreme mismatch", "MinDifference": 600, "MaxDifference": None, "SortOrder": 6},
    ]


# ──────────────────────────────────────────────────────────────────────────────
# SILVER_GAME
# ──────────────────────────────────────────────────────────────────────────────

SILVER_GAME_SCHEMA = pa.schema(
    [
        pa.field("SourceGameID", pa.string()),
        pa.field("GameDate", pa.date32()),
        pa.field("Date_SK", pa.int32()),
        pa.field("ResultCode", pa.string()),
        pa.field("WhiteScore", pa.float64()),
        pa.field("BlackScore", pa.float64()),
        pa.field("IsWhiteWin", pa.int8()),
        pa.field("IsBlackWin", pa.int8()),
        pa.field("IsDraw", pa.int8()),
        pa.field("WhiteRating_SK", pa.int16()),
        pa.field("BlackRating_SK", pa.int16()),
        pa.field("AbsRatingDifference", pa.int16()),
        pa.field("RatingDifferenceBucket_SK", pa.int8()),
        pa.field("TimeControlRaw", pa.string()),
        pa.field("TimeControl_SK", pa.int64()),
        pa.field("TerminationRaw", pa.string()),
        pa.field("Termination_SK", pa.int64()),
        pa.field("IsTimeForfeit", pa.int8()),
        pa.field("ECOCode", pa.string()),
        pa.field("OpeningName", pa.string()),
        pa.field("PlyCount", pa.int32()),
        pa.field("SourceMonth", pa.string()),
        pa.field("BronzeIngestionRunID", pa.string()),
        pa.field("SilverTransformRunID", pa.string()),
        pa.field("TransformVersion", pa.string()),
        pa.field("SchemaVersion", pa.string()),
    ]
)


def build_silver_game_rows(
    bronze_rows: list[dict[str, Any]],
    time_control_per_row: list[dict[str, Any]],
    termination_per_row: list[dict[str, Any]],
    transform_run_id: str,
) -> list[dict[str, Any]]:
    """Build silver_game fact rows from Bronze input and pre-parsed dimension results."""
    silver_rows: list[dict[str, Any]] = []
    for i, bronze_row in enumerate(bronze_rows):
        time_control = time_control_per_row[i]
        termination = termination_per_row[i]
        parsed_date = parse_game_date(bronze_row.get("UTCDateRaw"))
        white_rating = normalize_rating(bronze_row.get("WhiteRating_SK"))
        black_rating = normalize_rating(bronze_row.get("BlackRating_SK"))
        abs_rating_diff = abs(white_rating - black_rating)
        rating_bucket_sk = assign_rating_difference_bucket(abs_rating_diff)
        silver_rows.append(
            {
                "SourceGameID": bronze_row.get("SourceGameID"),
                "GameDate": parsed_date,
                "Date_SK": date_key(parsed_date),
                "ResultCode": bronze_row.get("ResultRaw"),
                "WhiteScore": bronze_row.get("WhiteScore"),
                "BlackScore": bronze_row.get("BlackScore"),
                "IsWhiteWin": bronze_row.get("IsWhiteWin"),
                "IsBlackWin": bronze_row.get("IsBlackWin"),
                "IsDraw": bronze_row.get("IsDraw"),
                "WhiteRating_SK": white_rating,
                "BlackRating_SK": black_rating,
                "AbsRatingDifference": abs_rating_diff,
                "RatingDifferenceBucket_SK": rating_bucket_sk,
                "TimeControlRaw": bronze_row.get("TimeControlRaw"),
                "TimeControl_SK": time_control["TimeControl_SK"],
                "TerminationRaw": bronze_row.get("TerminationRaw"),
                "Termination_SK": termination["Termination_SK"],
                "IsTimeForfeit": termination["IsTimeForfeit"],
                "ECOCode": bronze_row.get("ECOCode"),
                "OpeningName": bronze_row.get("OpeningName"),
                "PlyCount": bronze_row.get("PlyCount"),
                "SourceMonth": bronze_row.get("SourceMonth"),
                "BronzeIngestionRunID": bronze_row.get("IngestionRunID"),
                "SilverTransformRunID": transform_run_id,
                "TransformVersion": TRANSFORM_VERSION,
                "SchemaVersion": SCHEMA_VERSION,
            }
        )
    return silver_rows


# ──────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ──────────────────────────────────────────────────────────────────────────────

def validate_parquet_schema(output_path: Path, expected_schema: pa.Schema, label: str) -> tuple[str, list[str]]:
    actual_schema = pq.read_schema(output_path)
    messages: list[str] = []
    for expected_field in expected_schema:
        actual_index = actual_schema.get_field_index(expected_field.name)
        if actual_index == -1:
            messages.append(f"{label} is missing expected column {expected_field.name}.")
            continue
        actual_field = actual_schema.field(actual_index)
        if actual_field.type != expected_field.type:
            messages.append(
                f"{label}.{expected_field.name} expected {expected_field.type} but found {actual_field.type}."
            )
    extra_names = sorted(set(actual_schema.names) - set(expected_schema.names))
    if extra_names:
        messages.append(f"{label} has unexpected columns: {', '.join(extra_names)}.")
    if messages:
        return "fail", messages
    return "pass", [f"{label} schema matches the expected {SCHEMA_VERSION} contract."]


def validate_rows(
    bronze_rows: list[dict[str, Any]],
    silver_rows: list[dict[str, Any]],
    dim_time_control_rows: list[dict[str, Any]],
    dim_termination_rows: list[dict[str, Any]],
    dim_rating_difference_bucket_rows: list[dict[str, Any]],
) -> tuple[str, list[str], dict[str, int]]:
    messages: list[str] = []
    status = "pass"

    quality_counts = {
        "BronzeRowsRead": len(bronze_rows),
        "SilverRowsWritten": len(silver_rows),
        "InvalidDateRows": sum(1 for row in silver_rows if row["GameDate"] is None),
        "UnknownTimeControlRows": sum(1 for row in silver_rows if row["TimeControl_SK"] == 0),
        "UnknownTerminationRows": sum(1 for row in silver_rows if row["Termination_SK"] == 0),
        "TimeForfeitRows": sum(1 for row in silver_rows if row["IsTimeForfeit"] == 1),
        "UnknownWhiteRatingRows": sum(1 for row in silver_rows if row["WhiteRating_SK"] == UNKNOWN_RATING_SENTINEL),
        "UnknownBlackRatingRows": sum(1 for row in silver_rows if row["BlackRating_SK"] == UNKNOWN_RATING_SENTINEL),
    }

    # ── silver_game row integrity ────────────────────────────────────────────
    if len(bronze_rows) != len(silver_rows):
        status = "fail"
        messages.append("Silver row count does not equal Bronze row count.")

    source_ids = [row["SourceGameID"] for row in silver_rows]
    if any(sid is None for sid in source_ids):
        status = "fail"
        messages.append("One or more Silver rows have a missing SourceGameID.")
    if len(source_ids) != len(set(source_ids)):
        status = "fail"
        messages.append("SourceGameID is not unique in Silver output.")

    invalid_scores = [
        row["SourceGameID"]
        for row in silver_rows
        if row["WhiteScore"] is not None
        and row["BlackScore"] is not None
        and abs((row["WhiteScore"] + row["BlackScore"]) - 1.0) > 0.0001
    ]
    if invalid_scores:
        status = "fail"
        messages.append(f"{len(invalid_scores)} rows fail WhiteScore + BlackScore = 1.0.")

    invalid_flags = [
        row["SourceGameID"]
        for row in silver_rows
        if row["IsWhiteWin"] is not None
        and row["IsBlackWin"] is not None
        and row["IsDraw"] is not None
        and row["IsWhiteWin"] + row["IsBlackWin"] + row["IsDraw"] != 1
    ]
    if invalid_flags:
        status = "fail"
        messages.append(f"{len(invalid_flags)} rows fail win/draw flag validation.")

    # ── Rating field integrity ───────────────────────────────────────────────
    if any(row["WhiteRating_SK"] is None or not isinstance(row["WhiteRating_SK"], int) for row in silver_rows):
        status = "fail"
        messages.append("One or more WhiteRating_SK values are null or non-integer after normalization.")

    if any(row["BlackRating_SK"] is None or not isinstance(row["BlackRating_SK"], int) for row in silver_rows):
        status = "fail"
        messages.append("One or more BlackRating_SK values are null or non-integer after normalization.")

    if any(row["AbsRatingDifference"] is None for row in silver_rows):
        status = "fail"
        messages.append("One or more rows have a null AbsRatingDifference after normalization.")

    if any(row["AbsRatingDifference"] < 0 for row in silver_rows):
        status = "fail"
        messages.append("One or more rows have a negative AbsRatingDifference.")

    # ── Dimension referential integrity ─────────────────────────────────────
    time_control_keys = {row["TimeControl_SK"] for row in dim_time_control_rows}
    if any(row["TimeControl_SK"] not in time_control_keys for row in silver_rows):
        status = "fail"
        messages.append("One or more Silver rows do not map to dim_time_control.")

    termination_keys = {row["Termination_SK"] for row in dim_termination_rows}
    if any(row["Termination_SK"] not in termination_keys for row in silver_rows):
        status = "fail"
        messages.append("One or more Silver rows do not map to dim_termination.")

    bucket_keys = {row["RatingDifferenceBucket_SK"] for row in dim_rating_difference_bucket_rows}
    if any(row["RatingDifferenceBucket_SK"] not in bucket_keys for row in silver_rows):
        status = "fail"
        messages.append("One or more Silver rows do not map to dim_rating_difference_bucket.")

    if status == "pass":
        messages.append("All minimum Silver game row validation checks passed.")
    return status, messages, quality_counts


# ──────────────────────────────────────────────────────────────────────────────
# ORCHESTRATION
# ──────────────────────────────────────────────────────────────────────────────

def write_parquet(rows: list[dict[str, Any]], output_path: Path, schema: pa.Schema) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, output_path, compression="zstd")


def build_silver_outputs(
    bronze_rows: list[dict[str, Any]], transform_run_id: str
) -> dict[str, list[dict[str, Any]]]:
    time_control_per_row, dim_time_control = build_dim_time_control(bronze_rows)
    termination_per_row, dim_termination = build_dim_termination(bronze_rows)
    dim_rating_bucket = build_dim_rating_difference_bucket()
    silver_game = build_silver_game_rows(
        bronze_rows, time_control_per_row, termination_per_row, transform_run_id
    )
    return {
        "silver_game": silver_game,
        "dim_time_control": dim_time_control,
        "dim_termination": dim_termination,
        "dim_rating_difference_bucket": dim_rating_bucket,
    }


def transform(args: argparse.Namespace) -> dict[str, Any]:
    output_root = args.output_root.resolve()
    bronze_input = (
        args.bronze_input.resolve()
        if args.bronze_input
        else output_root / "bronze" / "game" / f"source_month={args.source_month}" / "bronze_game.parquet"
    )
    if not bronze_input.exists():
        raise FileNotFoundError(f"Bronze input does not exist: {bronze_input}")

    transform_run_id = args.transform_run_id or str(uuid.uuid4())
    started_at_utc = datetime.now(UTC).isoformat()

    bronze_rows = pq.read_table(bronze_input).to_pylist()
    outputs = build_silver_outputs(bronze_rows, transform_run_id)

    silver_game_output = output_root / "silver" / "game" / f"source_month={args.source_month}" / "silver_game.parquet"
    dim_time_control_output = output_root / "silver" / "dimensions" / "dim_time_control.parquet"
    dim_termination_output = output_root / "silver" / "dimensions" / "dim_termination.parquet"
    dim_rating_bucket_output = output_root / "silver" / "dimensions" / "dim_rating_difference_bucket.parquet"
    manifest_output = (
        output_root / "silver" / "manifests" / f"source_month={args.source_month}" / "silver_game_manifest.json"
    )

    write_parquet(outputs["silver_game"], silver_game_output, SILVER_GAME_SCHEMA)
    write_parquet(outputs["dim_time_control"], dim_time_control_output, DIM_TIME_CONTROL_SCHEMA)
    write_parquet(outputs["dim_termination"], dim_termination_output, DIM_TERMINATION_SCHEMA)
    write_parquet(outputs["dim_rating_difference_bucket"], dim_rating_bucket_output, DIM_RATING_DIFFERENCE_BUCKET_SCHEMA)

    validation_status, validation_messages, quality_counts = validate_rows(
        bronze_rows,
        outputs["silver_game"],
        outputs["dim_time_control"],
        outputs["dim_termination"],
        outputs["dim_rating_difference_bucket"],
    )

    schema_validations = [
        validate_parquet_schema(silver_game_output, SILVER_GAME_SCHEMA, "silver_game"),
        validate_parquet_schema(dim_time_control_output, DIM_TIME_CONTROL_SCHEMA, "dim_time_control"),
        validate_parquet_schema(dim_termination_output, DIM_TERMINATION_SCHEMA, "dim_termination"),
        validate_parquet_schema(dim_rating_bucket_output, DIM_RATING_DIFFERENCE_BUCKET_SCHEMA, "dim_rating_difference_bucket"),
    ]
    if any(s == "fail" for s, _ in schema_validations):
        validation_status = "fail"
    for _, msgs in schema_validations:
        validation_messages.extend(msgs)

    manifest = {
        "SilverTransformRunID": transform_run_id,
        "SourceMonth": args.source_month,
        "BronzeInputPath": str(bronze_input),
        "SilverGameOutputPath": str(silver_game_output),
        "DimTimeControlOutputPath": str(dim_time_control_output),
        "DimTerminationOutputPath": str(dim_termination_output),
        "DimRatingDifferenceBucketOutputPath": str(dim_rating_bucket_output),
        "StartedAtUTC": started_at_utc,
        "CompletedAtUTC": datetime.now(UTC).isoformat(),
        "TransformVersion": TRANSFORM_VERSION,
        "SchemaVersion": SCHEMA_VERSION,
        "QualityCounts": quality_counts,
        "DimTimeControlRowsWritten": len(outputs["dim_time_control"]),
        "DimTerminationRowsWritten": len(outputs["dim_termination"]),
        "DimRatingDifferenceBucketRowsWritten": len(outputs["dim_rating_difference_bucket"]),
        "ValidationStatus": validation_status,
        "ValidationMessages": validation_messages,
    }

    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Silver game and seed dimensions from Bronze game output.")
    parser.add_argument("--source-month", required=True)
    parser.add_argument("--output-root", default=Path("data"), type=Path)
    parser.add_argument("--bronze-input", default=None, type=Path)
    parser.add_argument("--transform-run-id", default=None)
    args = parser.parse_args()

    manifest = transform(args)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
