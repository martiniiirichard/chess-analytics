from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


# ------------------------------------------------------------------------------
# CONSTANTS
# ------------------------------------------------------------------------------

TRANSFORM_VERSION = "gold-game-0.1.0"
SCHEMA_VERSION = "gold-game-v1"
UNKNOWN_RATING_SENTINEL = 100

ECO_CATEGORY_NAMES: dict[str, str] = {
    "A": "Flank Openings",
    "B": "Semi-Open Games",
    "C": "Open Games",
    "D": "Closed Games",
    "E": "Indian Defenses",
}

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ------------------------------------------------------------------------------
# SHARED HELPERS
# ------------------------------------------------------------------------------

def stable_positive_key(value: str) -> int:
    """Deterministic 63-bit key; stable across reruns."""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


# ------------------------------------------------------------------------------
# DIM_DATE
# ------------------------------------------------------------------------------

DIM_DATE_SCHEMA = pa.schema(
    [
        pa.field("Date_SK", pa.int32()),
        pa.field("GameDate", pa.date32()),
        pa.field("Year", pa.int16()),
        pa.field("Month", pa.int8()),
        pa.field("MonthName", pa.string()),
        pa.field("Quarter", pa.int8()),
        pa.field("DayOfWeek", pa.int8()),
        pa.field("DayOfWeekName", pa.string()),
    ]
)


def build_dim_date(silver_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    members: dict[int, dict[str, Any]] = {}
    for row in silver_rows:
        sk = row.get("Date_SK")
        gd = row.get("GameDate")
        if sk is None or gd is None or sk in members:
            continue
        members[sk] = {
            "Date_SK": sk,
            "GameDate": gd,
            "Year": gd.year,
            "Month": gd.month,
            "MonthName": _MONTH_NAMES[gd.month - 1],
            "Quarter": (gd.month - 1) // 3 + 1,
            "DayOfWeek": gd.weekday(),
            "DayOfWeekName": _DOW_NAMES[gd.weekday()],
        }
    return sorted(members.values(), key=lambda r: r["Date_SK"])


# ------------------------------------------------------------------------------
# DIM_WHITE_RATING / DIM_BLACK_RATING
# Two separate dimension tables; same shape, different SK column names.
# SK column name matches the FK name in fact_game so Power BI auto-detects both
# relationships. Separate tables keep both relationships active simultaneously.
# ------------------------------------------------------------------------------

def _make_dim_rating_schema(sk_column: str) -> pa.Schema:
    return pa.schema(
        [
            pa.field(sk_column, pa.int16()),
            pa.field("RatingBand", pa.string()),
            pa.field("RatingBandMin", pa.int16()),
            pa.field("RatingBandMax", pa.int16()),
            pa.field("IsUnknown", pa.int8()),
        ]
    )

DIM_WHITE_RATING_SCHEMA = _make_dim_rating_schema("WhiteRating_SK")
DIM_BLACK_RATING_SCHEMA = _make_dim_rating_schema("BlackRating_SK")


def assign_rating_band(rating: int) -> dict[str, Any]:
    """Map an Elo rating to its 200-point band attributes."""
    if rating == UNKNOWN_RATING_SENTINEL:
        return {"RatingBand": "Unknown", "RatingBandMin": None, "RatingBandMax": None, "IsUnknown": 1}
    if rating < 800:
        return {"RatingBand": "Under 800", "RatingBandMin": 0, "RatingBandMax": 799, "IsUnknown": 0}
    band_min = (rating // 200) * 200
    if band_min >= 2200:
        return {"RatingBand": "2200+", "RatingBandMin": 2200, "RatingBandMax": None, "IsUnknown": 0}
    band_max = band_min + 199
    return {"RatingBand": f"{band_min}-{band_max}", "RatingBandMin": band_min, "RatingBandMax": band_max, "IsUnknown": 0}


def build_dim_rating(silver_rows: list[dict[str, Any]], rating_field: str) -> list[dict[str, Any]]:
    """Build a rating dimension from all distinct values of rating_field in Silver.

    The PK column in the output uses rating_field as its name so it matches
    the FK column name in fact_game - required for Power BI auto-detection.
    """
    members: dict[int, dict[str, Any]] = {}
    for row in silver_rows:
        sk = row.get(rating_field)
        if sk is not None and sk not in members:
            members[sk] = {rating_field: sk, **assign_rating_band(sk)}
    return sorted(members.values(), key=lambda r: r[rating_field])


# ------------------------------------------------------------------------------
# DIM_RATING_DIFFERENCE_BUCKET  (promoted from Silver, schema unchanged)
# ------------------------------------------------------------------------------

DIM_RATING_DIFFERENCE_BUCKET_SCHEMA = pa.schema(
    [
        pa.field("RatingDifferenceBucket_SK", pa.int8()),
        pa.field("RatingDifferenceBucketLabel", pa.string()),
        pa.field("MinDifference", pa.int16()),
        pa.field("MaxDifference", pa.int16()),
        pa.field("SortOrder", pa.int8()),
    ]
)


# ------------------------------------------------------------------------------
# DIM_TIME_CONTROL  (promoted from Silver, schema unchanged)
# ------------------------------------------------------------------------------

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


# ------------------------------------------------------------------------------
# DIM_TERMINATION  (promoted from Silver, schema unchanged)
# ------------------------------------------------------------------------------

DIM_TERMINATION_SCHEMA = pa.schema(
    [
        pa.field("Termination_SK", pa.int64()),
        pa.field("TerminationRaw", pa.string()),
        pa.field("TerminationLabel", pa.string()),
        pa.field("IsTimeForfeit", pa.int8()),
        pa.field("MappingStatus", pa.string()),
    ]
)


# ------------------------------------------------------------------------------
# DIM_ECO
# ------------------------------------------------------------------------------

DIM_ECO_SCHEMA = pa.schema(
    [
        pa.field("ECO_SK", pa.int64()),
        pa.field("ECOCode", pa.string()),
        pa.field("ECOCategory", pa.string()),
        pa.field("ECOCategoryName", pa.string()),
    ]
)


def build_dim_eco(
    silver_rows: list[dict[str, Any]],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Build dim_eco from distinct ECO codes in Silver.

    Returns (eco_sk_map: {eco_code: ECO_SK}, dim_rows).
    SK=0 Unknown row is pre-seeded; fact rows with missing ECO map to it.
    """
    members: dict[str, dict[str, Any]] = {}
    for row in silver_rows:
        code = (row.get("ECOCode") or "").strip()
        if code and code not in members:
            category = code[0].upper()
            members[code] = {
                "ECO_SK": stable_positive_key(f"eco|{code}"),
                "ECOCode": code,
                "ECOCategory": category,
                "ECOCategoryName": ECO_CATEGORY_NAMES.get(category, "Unknown"),
            }
    eco_sk_map = {code: m["ECO_SK"] for code, m in members.items()}
    dim_rows = (
        [{"ECO_SK": 0, "ECOCode": "Unknown", "ECOCategory": "Unknown", "ECOCategoryName": "Unknown"}]
        + sorted(members.values(), key=lambda r: r["ECOCode"])
    )
    return eco_sk_map, dim_rows


# ------------------------------------------------------------------------------
# DIM_OPENING_VARIATION
# ------------------------------------------------------------------------------

DIM_OPENING_VARIATION_SCHEMA = pa.schema(
    [
        pa.field("OpeningVariation_SK", pa.int64()),
        pa.field("OpeningName", pa.string()),
        pa.field("ECO_SK", pa.int64()),
    ]
)


def build_dim_opening_variation(
    silver_rows: list[dict[str, Any]],
    eco_sk_map: dict[str, int],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Build dim_opening_variation from distinct Lichess opening names in Silver.

    Returns (opening_sk_map: {opening_name: OpeningVariation_SK}, dim_rows).
    Each variation carries an ECO_SK FK to dim_eco.
    """
    members: dict[str, dict[str, Any]] = {}
    for row in silver_rows:
        name = (row.get("OpeningName") or "").strip()
        code = (row.get("ECOCode") or "").strip()
        if name and name not in members:
            members[name] = {
                "OpeningVariation_SK": stable_positive_key(f"opening|{name}"),
                "OpeningName": name,
                "ECO_SK": eco_sk_map.get(code, 0),
            }
    opening_sk_map = {name: m["OpeningVariation_SK"] for name, m in members.items()}
    dim_rows = (
        [{"OpeningVariation_SK": 0, "OpeningName": "Unknown", "ECO_SK": 0}]
        + sorted(members.values(), key=lambda r: r["OpeningName"])
    )
    return opening_sk_map, dim_rows


# ------------------------------------------------------------------------------
# FACT_GAME
# ------------------------------------------------------------------------------

FACT_GAME_SCHEMA = pa.schema(
    [
        pa.field("SourceGameID", pa.string()),
        pa.field("Date_SK", pa.int32()),
        pa.field("WhiteRating_SK", pa.int16()),
        pa.field("BlackRating_SK", pa.int16()),
        pa.field("RatingDifferenceBucket_SK", pa.int8()),
        pa.field("TimeControl_SK", pa.int64()),
        pa.field("Termination_SK", pa.int64()),
        pa.field("ECO_SK", pa.int64()),
        pa.field("OpeningVariation_SK", pa.int64()),
        pa.field("WhiteScore", pa.float64()),
        pa.field("BlackScore", pa.float64()),
        pa.field("IsWhiteWin", pa.int8()),
        pa.field("IsBlackWin", pa.int8()),
        pa.field("IsDraw", pa.int8()),
        pa.field("PlyCount", pa.int32()),
        pa.field("AbsRatingDifference", pa.int16()),
        pa.field("IsTimeForfeit", pa.int8()),
        pa.field("SourceMonth", pa.string()),
        pa.field("BronzeIngestionRunID", pa.string()),
        pa.field("SilverTransformRunID", pa.string()),
        pa.field("GoldTransformRunID", pa.string()),
        pa.field("GoldTransformVersion", pa.string()),
        pa.field("SchemaVersion", pa.string()),
    ]
)


def build_fact_game(
    silver_rows: list[dict[str, Any]],
    eco_sk_map: dict[str, int],
    opening_sk_map: dict[str, int],
    transform_run_id: str,
) -> list[dict[str, Any]]:
    """Build fact_game rows from Silver game rows and Gold dimension SK maps."""
    fact_rows: list[dict[str, Any]] = []
    for row in silver_rows:
        eco_code = (row.get("ECOCode") or "").strip()
        opening_name = (row.get("OpeningName") or "").strip()
        fact_rows.append(
            {
                "SourceGameID": row["SourceGameID"],
                "Date_SK": row["Date_SK"],
                "WhiteRating_SK": row["WhiteRating_SK"],
                "BlackRating_SK": row["BlackRating_SK"],
                "RatingDifferenceBucket_SK": row["RatingDifferenceBucket_SK"],
                "TimeControl_SK": row["TimeControl_SK"],
                "Termination_SK": row["Termination_SK"],
                "ECO_SK": eco_sk_map.get(eco_code, 0),
                "OpeningVariation_SK": opening_sk_map.get(opening_name, 0),
                "WhiteScore": row["WhiteScore"],
                "BlackScore": row["BlackScore"],
                "IsWhiteWin": row["IsWhiteWin"],
                "IsBlackWin": row["IsBlackWin"],
                "IsDraw": row["IsDraw"],
                "PlyCount": row["PlyCount"],
                "AbsRatingDifference": row["AbsRatingDifference"],
                "IsTimeForfeit": row["IsTimeForfeit"],
                "SourceMonth": row["SourceMonth"],
                "BronzeIngestionRunID": row["BronzeIngestionRunID"],
                "SilverTransformRunID": row["SilverTransformRunID"],
                "GoldTransformRunID": transform_run_id,
                "GoldTransformVersion": TRANSFORM_VERSION,
                "SchemaVersion": SCHEMA_VERSION,
            }
        )
    return fact_rows


# ------------------------------------------------------------------------------
# VALIDATION
# ------------------------------------------------------------------------------

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
    silver_rows: list[dict[str, Any]],
    fact_rows: list[dict[str, Any]],
    outputs: dict[str, list[dict[str, Any]]],
) -> tuple[str, list[str], dict[str, int]]:
    messages: list[str] = []
    status = "pass"

    quality_counts = {
        "SilverRowsRead": len(silver_rows),
        "FactRowsWritten": len(fact_rows),
        "DimDateRowsWritten": len(outputs["dim_date"]),
        "DimWhiteRatingRowsWritten": len(outputs["dim_white_rating"]),
        "DimBlackRatingRowsWritten": len(outputs["dim_black_rating"]),
        "DimECORowsWritten": len(outputs["dim_eco"]),
        "DimOpeningVariationRowsWritten": len(outputs["dim_opening_variation"]),
        "UnmappedECORows": sum(1 for r in fact_rows if r["ECO_SK"] == 0),
        "UnmappedOpeningRows": sum(1 for r in fact_rows if r["OpeningVariation_SK"] == 0),
    }

    # -- Fact row integrity ---------------------------------------------------
    if len(silver_rows) != len(fact_rows):
        status = "fail"
        messages.append("Fact row count does not equal Silver row count.")

    source_ids = [r["SourceGameID"] for r in fact_rows]
    if any(sid is None for sid in source_ids):
        status = "fail"
        messages.append("One or more fact rows have a missing SourceGameID.")
    if len(source_ids) != len(set(source_ids)):
        status = "fail"
        messages.append("SourceGameID is not unique in fact_game output.")

    # -- Dimension referential integrity -------------------------------------
    date_keys = {r["Date_SK"] for r in outputs["dim_date"]}
    if any(r["Date_SK"] is not None and r["Date_SK"] not in date_keys for r in fact_rows):
        status = "fail"
        messages.append("One or more fact rows do not map to dim_date.")

    white_keys = {r["WhiteRating_SK"] for r in outputs["dim_white_rating"]}
    if any(r["WhiteRating_SK"] not in white_keys for r in fact_rows):
        status = "fail"
        messages.append("One or more fact rows do not map to dim_white_rating.")

    black_keys = {r["BlackRating_SK"] for r in outputs["dim_black_rating"]}
    if any(r["BlackRating_SK"] not in black_keys for r in fact_rows):
        status = "fail"
        messages.append("One or more fact rows do not map to dim_black_rating.")

    time_control_keys = {r["TimeControl_SK"] for r in outputs["dim_time_control"]}
    if any(r["TimeControl_SK"] not in time_control_keys for r in fact_rows):
        status = "fail"
        messages.append("One or more fact rows do not map to dim_time_control.")

    termination_keys = {r["Termination_SK"] for r in outputs["dim_termination"]}
    if any(r["Termination_SK"] not in termination_keys for r in fact_rows):
        status = "fail"
        messages.append("One or more fact rows do not map to dim_termination.")

    bucket_keys = {r["RatingDifferenceBucket_SK"] for r in outputs["dim_rating_difference_bucket"]}
    if any(r["RatingDifferenceBucket_SK"] not in bucket_keys for r in fact_rows):
        status = "fail"
        messages.append("One or more fact rows do not map to dim_rating_difference_bucket.")

    eco_keys = {r["ECO_SK"] for r in outputs["dim_eco"]}
    if any(r["ECO_SK"] not in eco_keys for r in fact_rows):
        status = "fail"
        messages.append("One or more fact rows do not map to dim_eco.")

    opening_keys = {r["OpeningVariation_SK"] for r in outputs["dim_opening_variation"]}
    if any(r["OpeningVariation_SK"] not in opening_keys for r in fact_rows):
        status = "fail"
        messages.append("One or more fact rows do not map to dim_opening_variation.")

    if status == "pass":
        messages.append("All minimum Gold game row validation checks passed.")
    return status, messages, quality_counts


# ------------------------------------------------------------------------------
# ORCHESTRATION
# ------------------------------------------------------------------------------

def write_parquet(rows: list[dict[str, Any]], output_path: Path, schema: pa.Schema) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, output_path, compression="zstd")


def build_gold_outputs(
    silver_rows: list[dict[str, Any]],
    silver_dim_root: Path,
    transform_run_id: str,
) -> dict[str, list[dict[str, Any]]]:
    eco_sk_map, dim_eco = build_dim_eco(silver_rows)
    opening_sk_map, dim_opening = build_dim_opening_variation(silver_rows, eco_sk_map)
    return {
        "fact_game": build_fact_game(silver_rows, eco_sk_map, opening_sk_map, transform_run_id),
        "dim_date": build_dim_date(silver_rows),
        "dim_white_rating": build_dim_rating(silver_rows, "WhiteRating_SK"),
        "dim_black_rating": build_dim_rating(silver_rows, "BlackRating_SK"),
        "dim_eco": dim_eco,
        "dim_opening_variation": dim_opening,
        "dim_time_control": pq.read_table(silver_dim_root / "dim_time_control.parquet").to_pylist(),
        "dim_termination": pq.read_table(silver_dim_root / "dim_termination.parquet").to_pylist(),
        "dim_rating_difference_bucket": pq.read_table(silver_dim_root / "dim_rating_difference_bucket.parquet").to_pylist(),
    }


def transform(args: argparse.Namespace) -> dict[str, Any]:
    output_root = args.output_root.resolve()
    silver_input = (
        args.silver_input.resolve()
        if args.silver_input
        else output_root / "silver" / "game" / f"source_month={args.source_month}" / "silver_game.parquet"
    )
    silver_dim_root = output_root / "silver" / "dimensions"

    if not silver_input.exists():
        raise FileNotFoundError(f"Silver input does not exist: {silver_input}")

    transform_run_id = args.transform_run_id or str(uuid.uuid4())
    started_at_utc = datetime.now(UTC).isoformat()

    silver_rows = pq.read_table(silver_input).to_pylist()
    outputs = build_gold_outputs(silver_rows, silver_dim_root, transform_run_id)

    gold_root = output_root / "gold"
    fact_output          = gold_root / "game" / f"source_month={args.source_month}" / "fact_game.parquet"
    dim_date_output      = gold_root / "dimensions" / "dim_date.parquet"
    dim_white_output     = gold_root / "dimensions" / "dim_white_rating.parquet"
    dim_black_output     = gold_root / "dimensions" / "dim_black_rating.parquet"
    dim_tc_output        = gold_root / "dimensions" / "dim_time_control.parquet"
    dim_term_output      = gold_root / "dimensions" / "dim_termination.parquet"
    dim_bucket_output    = gold_root / "dimensions" / "dim_rating_difference_bucket.parquet"
    dim_eco_output       = gold_root / "dimensions" / "dim_eco.parquet"
    dim_opening_output   = gold_root / "dimensions" / "dim_opening_variation.parquet"
    manifest_output      = gold_root / "manifests" / f"source_month={args.source_month}" / "gold_game_manifest.json"

    write_parquet(outputs["fact_game"],                 fact_output,       FACT_GAME_SCHEMA)
    write_parquet(outputs["dim_date"],                  dim_date_output,   DIM_DATE_SCHEMA)
    write_parquet(outputs["dim_white_rating"],          dim_white_output,  DIM_WHITE_RATING_SCHEMA)
    write_parquet(outputs["dim_black_rating"],          dim_black_output,  DIM_BLACK_RATING_SCHEMA)
    write_parquet(outputs["dim_time_control"],          dim_tc_output,     DIM_TIME_CONTROL_SCHEMA)
    write_parquet(outputs["dim_termination"],           dim_term_output,   DIM_TERMINATION_SCHEMA)
    write_parquet(outputs["dim_rating_difference_bucket"], dim_bucket_output, DIM_RATING_DIFFERENCE_BUCKET_SCHEMA)
    write_parquet(outputs["dim_eco"],                   dim_eco_output,    DIM_ECO_SCHEMA)
    write_parquet(outputs["dim_opening_variation"],     dim_opening_output, DIM_OPENING_VARIATION_SCHEMA)

    validation_status, validation_messages, quality_counts = validate_rows(
        silver_rows, outputs["fact_game"], outputs
    )

    schema_validations = [
        validate_parquet_schema(fact_output,       FACT_GAME_SCHEMA,                   "fact_game"),
        validate_parquet_schema(dim_date_output,   DIM_DATE_SCHEMA,                    "dim_date"),
        validate_parquet_schema(dim_white_output,  DIM_WHITE_RATING_SCHEMA,            "dim_white_rating"),
        validate_parquet_schema(dim_black_output,  DIM_BLACK_RATING_SCHEMA,            "dim_black_rating"),
        validate_parquet_schema(dim_tc_output,     DIM_TIME_CONTROL_SCHEMA,            "dim_time_control"),
        validate_parquet_schema(dim_term_output,   DIM_TERMINATION_SCHEMA,             "dim_termination"),
        validate_parquet_schema(dim_bucket_output, DIM_RATING_DIFFERENCE_BUCKET_SCHEMA, "dim_rating_difference_bucket"),
        validate_parquet_schema(dim_eco_output,    DIM_ECO_SCHEMA,                     "dim_eco"),
        validate_parquet_schema(dim_opening_output, DIM_OPENING_VARIATION_SCHEMA,      "dim_opening_variation"),
    ]
    if any(s == "fail" for s, _ in schema_validations):
        validation_status = "fail"
    for _, msgs in schema_validations:
        validation_messages.extend(msgs)

    manifest = {
        "GoldTransformRunID": transform_run_id,
        "SourceMonth": args.source_month,
        "SilverInputPath": str(silver_input),
        "FactGameOutputPath": str(fact_output),
        "StartedAtUTC": started_at_utc,
        "CompletedAtUTC": datetime.now(UTC).isoformat(),
        "TransformVersion": TRANSFORM_VERSION,
        "SchemaVersion": SCHEMA_VERSION,
        "QualityCounts": quality_counts,
        "ValidationStatus": validation_status,
        "ValidationMessages": validation_messages,
    }

    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Gold game star schema from Silver game output.")
    parser.add_argument("--source-month", required=True)
    parser.add_argument("--output-root", default=Path("data"), type=Path)
    parser.add_argument("--silver-input", default=None, type=Path)
    parser.add_argument("--transform-run-id", default=None)
    args = parser.parse_args()

    manifest = transform(args)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
