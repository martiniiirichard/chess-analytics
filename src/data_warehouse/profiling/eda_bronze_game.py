from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import polars as pl


EDA_VERSION = "bronze-game-eda-0.1.0"

LICHESS_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,20}$")
ECO_CODE_PATTERN = re.compile(r"^[A-E]\d{2}$")
TIME_CONTROL_PATTERN = re.compile(r"^\d+\+\d+$")


def null_and_blank_profile(df: pl.DataFrame) -> dict:
    result = {}
    for col in df.columns:
        null_count = df[col].null_count()
        blank_count = 0
        if df[col].dtype == pl.Utf8:
            blank_count = df.filter(pl.col(col).str.strip_chars() == "").height
        result[col] = {"null_count": null_count, "blank_count": blank_count}
    return result


def categorical_profile(df: pl.DataFrame, col: str, top_n: int = 20) -> dict:
    if col not in df.columns:
        return {}
    series = df[col]
    value_counts = series.value_counts(sort=True).head(top_n)
    return {
        "distinct_count": series.n_unique(),
        "null_count": series.null_count(),
        "top_values": value_counts.to_dicts(),
    }


def numeric_profile(df: pl.DataFrame, col: str) -> dict:
    if col not in df.columns:
        return {}
    series = df[col]
    non_null = series.drop_nulls()
    return {
        "null_count": series.null_count(),
        "min": non_null.min() if non_null.len() > 0 else None,
        "max": non_null.max() if non_null.len() > 0 else None,
        "mean": round(non_null.mean(), 2) if non_null.len() > 0 else None,
        "median": non_null.median() if non_null.len() > 0 else None,
        "zero_count": df.filter(pl.col(col) == 0).height,
    }


def player_name_issues(df: pl.DataFrame) -> dict:
    result = {}
    for col in ("WhitePlayerName", "BlackPlayerName"):
        if col not in df.columns:
            continue
        non_null = df.filter(pl.col(col).is_not_null())
        invalid_rows = non_null.filter(
            ~pl.col(col).str.contains(r"^[a-zA-Z0-9_\-]{1,20}$")
        )
        result[col] = {
            "total_non_null": non_null.height,
            "invalid_format_count": invalid_rows.height,
            "sample_invalid": invalid_rows[col].head(5).to_list(),
        }
    return result


def eco_code_issues(df: pl.DataFrame) -> dict:
    if "ECOCode" not in df.columns:
        return {}
    non_null = df.filter(pl.col("ECOCode").is_not_null())
    invalid = non_null.filter(~pl.col("ECOCode").str.contains(r"^[A-E]\d{2}$"))
    return {
        "total_non_null": non_null.height,
        "invalid_pattern_count": invalid.height,
        "sample_invalid": invalid["ECOCode"].head(5).to_list(),
        "distinct_count": non_null["ECOCode"].n_unique(),
        "top_values": non_null["ECOCode"].value_counts(sort=True).head(10).to_dicts(),
    }


def time_control_issues(df: pl.DataFrame) -> dict:
    if "TimeControlRaw" not in df.columns:
        return {}
    non_null = df.filter(pl.col("TimeControlRaw").is_not_null())
    increment_format = non_null.filter(pl.col("TimeControlRaw").str.contains(r"^\d+\+\d+$"))
    other_format = non_null.filter(~pl.col("TimeControlRaw").str.contains(r"^\d+\+\d+$"))
    return {
        "total_non_null": non_null.height,
        "increment_format_count": increment_format.height,
        "other_format_count": other_format.height,
        "other_format_distinct_values": other_format["TimeControlRaw"].unique().to_list(),
    }


def opening_name_issues(df: pl.DataFrame) -> dict:
    if "OpeningName" not in df.columns:
        return {}
    non_null = df.filter(pl.col("OpeningName").is_not_null())
    non_ascii = non_null.filter(pl.col("OpeningName").str.contains(r"[^\x00-\x7F]"))
    return {
        "total_non_null": non_null.height,
        "non_ascii_count": non_ascii.height,
        "sample_non_ascii": non_ascii["OpeningName"].head(5).to_list(),
        "distinct_count": non_null["OpeningName"].n_unique(),
        "top_values": non_null["OpeningName"].value_counts(sort=True).head(10).to_dicts(),
    }


def score_flag_validation(df: pl.DataFrame) -> dict:
    score_invalid = df.filter(
        pl.col("WhiteScore").is_not_null()
        & pl.col("BlackScore").is_not_null()
        & ((pl.col("WhiteScore") + pl.col("BlackScore") - 1.0).abs() > 0.0001)
    ).height

    flag_invalid = df.filter(
        pl.col("IsWhiteWin").is_not_null()
        & pl.col("IsBlackWin").is_not_null()
        & pl.col("IsDraw").is_not_null()
        & ((pl.col("IsWhiteWin") + pl.col("IsBlackWin") + pl.col("IsDraw")) != 1)
    ).height

    unknown_result = df.filter(
        ~pl.col("ResultRaw").is_in(["1-0", "0-1", "1/2-1/2"])
    ).height

    return {
        "score_sum_invalid_rows": score_invalid,
        "win_draw_flag_invalid_rows": flag_invalid,
        "unknown_result_code_rows": unknown_result,
    }


def source_game_id_profile(df: pl.DataFrame) -> dict:
    if "SourceGameID" not in df.columns:
        return {}
    total = df.height
    unique = df["SourceGameID"].n_unique()
    null_count = df["SourceGameID"].null_count()
    return {
        "total_rows": total,
        "unique_ids": unique,
        "null_count": null_count,
        "duplicate_count": total - unique - null_count,
    }


def rating_distribution_bands(df: pl.DataFrame, col: str) -> dict:
    if col not in df.columns:
        return {}
    non_null = df.filter(pl.col(col).is_not_null())[col]
    bands = {
        "under_800": df.filter(pl.col(col) < 800).height,
        "800_999": df.filter((pl.col(col) >= 800) & (pl.col(col) <= 999)).height,
        "1000_1199": df.filter((pl.col(col) >= 1000) & (pl.col(col) <= 1199)).height,
        "1200_1399": df.filter((pl.col(col) >= 1200) & (pl.col(col) <= 1399)).height,
        "1400_1599": df.filter((pl.col(col) >= 1400) & (pl.col(col) <= 1599)).height,
        "1600_1799": df.filter((pl.col(col) >= 1600) & (pl.col(col) <= 1799)).height,
        "1800_1999": df.filter((pl.col(col) >= 1800) & (pl.col(col) <= 1999)).height,
        "2000_2199": df.filter((pl.col(col) >= 2000) & (pl.col(col) <= 2199)).height,
        "2200_plus": df.filter(pl.col(col) >= 2200).height,
    }
    return bands


def run_eda(bronze_path: Path, output_path: Path | None, source_month: str) -> dict:
    df = pl.read_parquet(bronze_path)

    report: dict = {
        "EDAVersion": EDA_VERSION,
        "SourceMonth": source_month,
        "BronzePath": str(bronze_path),
        "RunAtUTC": datetime.now(UTC).isoformat(),
        "RowCount": df.height,
        "ColumnCount": df.width,
        "Columns": df.columns,
    }

    report["NullAndBlankProfile"] = null_and_blank_profile(df)

    report["ResultRawProfile"] = categorical_profile(df, "ResultRaw")
    report["TerminationRawProfile"] = categorical_profile(df, "TerminationRaw")

    report["ScoreFlagValidation"] = score_flag_validation(df)
    report["SourceGameIDProfile"] = source_game_id_profile(df)

    report["WhiteRatingSKProfile"] = numeric_profile(df, "WhiteRating_SK")
    report["BlackRatingSKProfile"] = numeric_profile(df, "BlackRating_SK")
    report["AbsRatingDifferenceProfile"] = numeric_profile(df, "AbsRatingDifference")
    report["PlyCountProfile"] = numeric_profile(df, "PlyCount")

    report["WhiteRatingDistribution"] = rating_distribution_bands(df, "WhiteRating_SK")
    report["BlackRatingDistribution"] = rating_distribution_bands(df, "BlackRating_SK")

    report["PlayerNameIssues"] = player_name_issues(df)
    report["ECOCodeProfile"] = eco_code_issues(df)
    report["TimeControlProfile"] = time_control_issues(df)
    report["OpeningNameProfile"] = opening_name_issues(df)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    return report


def print_summary(report: dict) -> None:
    print(f"\n=== Bronze Game EDA — {report['SourceMonth']} ===")
    print(f"Rows: {report['RowCount']:,}  |  Columns: {report['ColumnCount']}")

    print("\n--- Null / Blank Counts (non-zero only) ---")
    for col, counts in report["NullAndBlankProfile"].items():
        if counts["null_count"] > 0 or counts["blank_count"] > 0:
            print(f"  {col}: null={counts['null_count']:,}  blank={counts['blank_count']:,}")

    print("\n--- Score / Flag Validation ---")
    for k, v in report["ScoreFlagValidation"].items():
        flag = "  FAIL" if v > 0 else "  ok"
        print(f"  {k}: {v:,}{flag}")

    print("\n--- SourceGameID ---")
    sid = report["SourceGameIDProfile"]
    print(f"  unique={sid['unique_ids']:,}  nulls={sid['null_count']:,}  duplicates={sid['duplicate_count']:,}")

    print("\n--- ResultRaw Distribution ---")
    for row in report["ResultRawProfile"].get("top_values", []):
        print(f"  {row.get('ResultRaw', row)}: {row.get('count', '')}")

    print("\n--- TerminationRaw Distribution ---")
    for row in report["TerminationRawProfile"].get("top_values", []):
        print(f"  {row.get('TerminationRaw', row)}: {row.get('count', '')}")

    print("\n--- Rating Ranges ---")
    for label, profile in [("White", report["WhiteRatingSKProfile"]), ("Black", report["BlackRatingSKProfile"])]:
        print(f"  {label}: min={profile['min']}  max={profile['max']}  mean={profile['mean']}  nulls={profile['null_count']:,}")

    print("\n--- White Rating Distribution ---")
    for band, count in report["WhiteRatingDistribution"].items():
        print(f"  {band}: {count:,}")

    print("\n--- Player Name Issues ---")
    for col, info in report["PlayerNameIssues"].items():
        print(f"  {col}: invalid_format={info['invalid_format_count']:,}")
        if info["sample_invalid"]:
            print(f"    samples: {info['sample_invalid']}")

    print("\n--- ECO Code Profile ---")
    eco = report["ECOCodeProfile"]
    print(f"  distinct={eco.get('distinct_count', 0)}  invalid_pattern={eco.get('invalid_pattern_count', 0):,}")

    print("\n--- Time Control Profile ---")
    tc = report["TimeControlProfile"]
    print(f"  increment_format={tc.get('increment_format_count', 0):,}  other_format={tc.get('other_format_count', 0):,}")
    if tc.get("other_format_distinct_values"):
        print(f"  other values: {tc['other_format_distinct_values']}")

    print("\n--- Opening Name Profile ---")
    op = report["OpeningNameProfile"]
    print(f"  distinct={op.get('distinct_count', 0):,}  non_ascii={op.get('non_ascii_count', 0):,}")

    print("\n--- PlyCount ---")
    pc = report["PlyCountProfile"]
    print(f"  min={pc['min']}  max={pc['max']}  mean={pc['mean']}  nulls={pc['null_count']:,}  zeros={pc['zero_count']:,}")


def main() -> None:
    parser = argparse.ArgumentParser(description="EDA profile of Bronze game Parquet.")
    parser.add_argument("--source-month", required=True)
    parser.add_argument("--output-root", default=Path("data"), type=Path)
    parser.add_argument("--bronze-input", default=None, type=Path)
    parser.add_argument("--no-save", action="store_true", help="Print only, do not write report file.")
    args = parser.parse_args()

    output_root = args.output_root.resolve()
    bronze_path = (
        args.bronze_input.resolve()
        if args.bronze_input
        else output_root / "bronze" / "game" / f"source_month={args.source_month}" / "bronze_game.parquet"
    )

    output_path = None if args.no_save else (
        output_root / "bronze" / "eda" / f"source_month={args.source_month}" / "bronze_game_eda.json"
    )

    report = run_eda(bronze_path, output_path, args.source_month)
    print_summary(report)

    if output_path:
        print(f"\nFull report saved to: {output_path}")


if __name__ == "__main__":
    main()
