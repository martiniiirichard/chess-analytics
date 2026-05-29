from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq
import zstandard


PARSER_VERSION = "bronze-game-0.1.0"
SCHEMA_VERSION = "bronze-game-v1"

# Convert PGN result notation into additive analytic fields.
# This makes score percentage and win/draw rates simple semantic model measures.
RESULT_MAP = {
    "1-0": (1.0, 0.0, 1, 0, 0),
    "0-1": (0.0, 1.0, 0, 1, 0),
    "1/2-1/2": (0.5, 0.5, 0, 0, 1),
}

# Lichess PGN files use standard tag pairs followed by movetext. The regexes below
# intentionally support Bronze extraction only; they are not a legal chess parser.
TAG_PATTERN = re.compile(r'^\[(?P<key>[A-Za-z0-9_]+)\s+"(?P<value>.*)"\]$')
COMMENT_PATTERN = re.compile(r"\{[^}]*\}")
VARIATION_PATTERN = re.compile(r"\([^)]*\)")
MOVE_NUMBER_PATTERN = re.compile(r"^\d+\.(\.\.)?$")
RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}

BRONZE_GAME_SCHEMA = pa.schema(
    [
        pa.field("SourceGameID", pa.string()),
        pa.field("SiteURL", pa.string()),
        pa.field("EventRaw", pa.string()),
        pa.field("UTCDateRaw", pa.string()),
        pa.field("UTCTimeRaw", pa.string()),
        pa.field("WhitePlayerName", pa.string()),
        pa.field("BlackPlayerName", pa.string()),
        pa.field("ResultRaw", pa.string()),
        pa.field("WhiteScore", pa.float64()),
        pa.field("BlackScore", pa.float64()),
        pa.field("IsWhiteWin", pa.int8()),
        pa.field("IsBlackWin", pa.int8()),
        pa.field("IsDraw", pa.int8()),
        pa.field("WhiteEloRaw", pa.string()),
        pa.field("BlackEloRaw", pa.string()),
        pa.field("WhiteRating_SK", pa.int16()),
        pa.field("BlackRating_SK", pa.int16()),
        pa.field("AbsRatingDifference", pa.int16()),
        pa.field("RatingDifferenceBucket_SK", pa.int8()),
        pa.field("WhiteRatingDiffRaw", pa.string()),
        pa.field("BlackRatingDiffRaw", pa.string()),
        pa.field("ECOCode", pa.string()),
        pa.field("OpeningName", pa.string()),
        pa.field("TimeControlRaw", pa.string()),
        pa.field("TerminationRaw", pa.string()),
        pa.field("PlyCount", pa.int16()),
        pa.field("SourceMonth", pa.string()),
        pa.field("SourceDataset", pa.string()),
        pa.field("SourceFileName", pa.string()),
        pa.field("SourceFileSHA256", pa.string()),
        pa.field("IngestionRunID", pa.string()),
        pa.field("ParserVersion", pa.string()),
        pa.field("SchemaVersion", pa.string()),
    ]
)

RAW_GAME_SAMPLE_SCHEMA = pa.schema(
    [
        pa.field("SourceMonth", pa.string()),
        pa.field("SourceDataset", pa.string()),
        pa.field("SampleRank", pa.int8()),
        pa.field("SourceGameID", pa.string()),
        pa.field("RawPGNText", pa.string()),
        pa.field("SourceURL", pa.string()),
        pa.field("SourceFileName", pa.string()),
        pa.field("SourceFileSHA256", pa.string()),
        pa.field("CompressedSizeBytes", pa.int64()),
        pa.field("ParserVersion", pa.string()),
        pa.field("CapturedAtUTC", pa.string()),
        pa.field("IngestionRunID", pa.string()),
    ]
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def source_game_id(site_url: str | None) -> str | None:
    if not site_url:
        return None
    return site_url.rstrip("/").split("/")[-1] or None


def rating_difference_bucket_key(abs_difference: int | None) -> int | None:
    """Map absolute rating gap into the approved rating-difference dimension keys."""
    if abs_difference is None:
        return None
    if abs_difference <= 49:
        return 1
    if abs_difference <= 99:
        return 2
    if abs_difference <= 199:
        return 3
    if abs_difference <= 399:
        return 4
    if abs_difference <= 599:
        return 5
    return 6


def open_pgn_stream(path: Path):
    compressed = path.open("rb")
    stream = zstandard.ZstdDecompressor().stream_reader(compressed)
    text = io.TextIOWrapper(stream, encoding="utf-8", errors="replace")
    return compressed, text


def iter_pgn_blocks(text_stream: io.TextIOWrapper) -> Iterator[str]:
    """Yield PGN game text blocks while preserving decompressed source text.

    Lichess exports each game as a PGN block beginning with an Event tag. Using
    that boundary is much faster than full chess parsing for game-grain Bronze.
    """
    current_lines: list[str] = []
    for line in text_stream:
        if line.startswith("[Event ") and current_lines:
            yield "".join(current_lines).strip() + "\n"
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        yield "".join(current_lines).strip() + "\n"


def parse_pgn_block(pgn_text: str) -> tuple[dict[str, str], int] | None:
    """Extract PGN tags and approximate ply count without validating move legality."""
    headers: dict[str, str] = {}
    movetext_lines: list[str] = []
    in_movetext = False

    for line in pgn_text.splitlines():
        stripped = line.strip()
        if not stripped:
            if headers:
                in_movetext = True
            continue

        if not in_movetext and stripped.startswith("["):
            match = TAG_PATTERN.match(stripped)
            if match:
                headers[match.group("key")] = match.group("value")
            continue

        in_movetext = True
        movetext_lines.append(stripped)

    if not headers:
        return None

    return headers, count_ply(" ".join(movetext_lines))


def count_ply(movetext: str) -> int:
    """Count move tokens for game-grain analytics, not board-state reconstruction."""
    text = COMMENT_PATTERN.sub(" ", movetext)
    text = VARIATION_PATTERN.sub(" ", text)
    ply_count = 0

    for token in text.split():
        token = token.strip()
        if not token:
            continue
        if token in RESULT_TOKENS:
            continue
        if MOVE_NUMBER_PATTERN.match(token):
            continue
        if token.startswith("$"):
            continue
        ply_count += 1

    return ply_count


def game_to_row(
    headers: dict[str, str],
    ply_count: int,
    source_month: str,
    source_dataset: str,
    source_file_name: str,
    source_file_sha256: str,
    ingestion_run_id: str,
) -> dict[str, Any]:
    """Convert one parsed PGN block into the enforced Bronze game schema."""
    white_elo = parse_int(headers.get("WhiteElo"))
    black_elo = parse_int(headers.get("BlackElo"))
    abs_rating_difference = (
        abs(white_elo - black_elo) if white_elo is not None and black_elo is not None else None
    )
    result = headers.get("Result", "")
    white_score, black_score, is_white_win, is_black_win, is_draw = RESULT_MAP.get(
        result, (None, None, None, None, None)
    )

    return {
        "SourceGameID": source_game_id(headers.get("Site")),
        "SiteURL": headers.get("Site"),
        "EventRaw": headers.get("Event"),
        "UTCDateRaw": headers.get("UTCDate"),
        "UTCTimeRaw": headers.get("UTCTime"),
        "WhitePlayerName": headers.get("White"),
        "BlackPlayerName": headers.get("Black"),
        "ResultRaw": result,
        "WhiteScore": white_score,
        "BlackScore": black_score,
        "IsWhiteWin": is_white_win,
        "IsBlackWin": is_black_win,
        "IsDraw": is_draw,
        "WhiteEloRaw": headers.get("WhiteElo"),
        "BlackEloRaw": headers.get("BlackElo"),
        "WhiteRating_SK": white_elo,
        "BlackRating_SK": black_elo,
        "AbsRatingDifference": abs_rating_difference,
        "RatingDifferenceBucket_SK": rating_difference_bucket_key(abs_rating_difference),
        "WhiteRatingDiffRaw": headers.get("WhiteRatingDiff"),
        "BlackRatingDiffRaw": headers.get("BlackRatingDiff"),
        "ECOCode": headers.get("ECO"),
        "OpeningName": headers.get("Opening"),
        "TimeControlRaw": headers.get("TimeControl"),
        "TerminationRaw": headers.get("Termination"),
        "PlyCount": ply_count,
        "SourceMonth": source_month,
        "SourceDataset": source_dataset,
        "SourceFileName": source_file_name,
        "SourceFileSHA256": source_file_sha256,
        "IngestionRunID": ingestion_run_id,
        "ParserVersion": PARSER_VERSION,
        "SchemaVersion": SCHEMA_VERSION,
    }


def validate_rows(rows: list[dict[str, Any]], raw_sample_count: int) -> tuple[str, list[str]]:
    messages: list[str] = []
    status = "pass"

    if not rows:
        return "fail", ["No bronze game rows were written."]

    if raw_sample_count < min(10, len(rows)):
        status = "fail"
        messages.append("Raw game sample did not capture the expected number of games.")

    source_ids = [row["SourceGameID"] for row in rows]
    if any(source_id is None for source_id in source_ids):
        status = "fail"
        messages.append("One or more rows have a missing SourceGameID.")
    if len(source_ids) != len(set(source_ids)):
        status = "fail"
        messages.append("SourceGameID is not unique within the file.")

    bad_results = [row["SourceGameID"] for row in rows if row["WhiteScore"] is None]
    if bad_results:
        status = "fail"
        messages.append(f"{len(bad_results)} rows have unmapped ResultRaw values.")

    bad_score_sum = [
        row["SourceGameID"]
        for row in rows
        if row["WhiteScore"] is not None
        and row["BlackScore"] is not None
        and abs((row["WhiteScore"] + row["BlackScore"]) - 1.0) > 0.0001
    ]
    if bad_score_sum:
        status = "fail"
        messages.append(f"{len(bad_score_sum)} rows fail WhiteScore + BlackScore = 1.0.")

    bad_flags = [
        row["SourceGameID"]
        for row in rows
        if row["IsWhiteWin"] is not None
        and row["IsBlackWin"] is not None
        and row["IsDraw"] is not None
        and row["IsWhiteWin"] + row["IsBlackWin"] + row["IsDraw"] != 1
    ]
    if bad_flags:
        status = "fail"
        messages.append(f"{len(bad_flags)} rows fail win/draw flag validation.")

    bad_rating_difference = [
        row["SourceGameID"]
        for row in rows
        if row["AbsRatingDifference"] is not None and row["AbsRatingDifference"] < 0
    ]
    if bad_rating_difference:
        status = "fail"
        messages.append(f"{len(bad_rating_difference)} rows have negative AbsRatingDifference.")

    if status == "pass":
        messages.append("All minimum Bronze game validation checks passed.")
    return status, messages


def write_parquet(rows: list[dict[str, Any]], output_path: Path, schema: pa.Schema) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, output_path, compression="zstd")


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

    actual_names = set(actual_schema.names)
    expected_names = set(expected_schema.names)
    extra_names = sorted(actual_names - expected_names)
    if extra_names:
        messages.append(f"{label} has unexpected columns: {', '.join(extra_names)}.")

    if messages:
        return "fail", messages
    return "pass", [f"{label} schema matches the expected {SCHEMA_VERSION} contract."]


def ingest(args: argparse.Namespace) -> dict[str, Any]:
    input_path = args.input.resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    output_root = args.output_root.resolve()
    source_file_sha256 = sha256_file(input_path)
    source_file_name = input_path.name
    ingestion_run_id = args.ingestion_run_id or str(uuid.uuid4())
    download_timestamp_utc = datetime.now(UTC).isoformat()

    bronze_rows: list[dict[str, Any]] = []
    raw_sample_rows: list[dict[str, Any]] = []
    games_failed = 0

    compressed, text_stream = open_pgn_stream(input_path)
    with compressed, text_stream:
        for pgn_text in iter_pgn_blocks(text_stream):
            try:
                parsed_game = parse_pgn_block(pgn_text)
            except Exception:
                games_failed += 1
                continue
            if parsed_game is None:
                games_failed += 1
                continue
            headers, ply_count = parsed_game

            if len(raw_sample_rows) < args.raw_sample_size:
                raw_sample_rows.append(
                    {
                        "SourceMonth": args.source_month,
                        "SourceDataset": args.source_dataset,
                        "SampleRank": len(raw_sample_rows) + 1,
                        "SourceGameID": source_game_id(headers.get("Site")),
                        "RawPGNText": pgn_text,
                        "SourceURL": args.source_url,
                        "SourceFileName": source_file_name,
                        "SourceFileSHA256": source_file_sha256,
                        "CompressedSizeBytes": input_path.stat().st_size,
                        "ParserVersion": PARSER_VERSION,
                        "CapturedAtUTC": datetime.now(UTC).isoformat(),
                        "IngestionRunID": ingestion_run_id,
                    }
                )

            bronze_rows.append(
                game_to_row(
                    headers,
                    ply_count,
                    args.source_month,
                    args.source_dataset,
                    source_file_name,
                    source_file_sha256,
                    ingestion_run_id,
                )
            )

    validation_status, validation_messages = validate_rows(bronze_rows, len(raw_sample_rows))

    bronze_output = output_root / "bronze" / "game" / f"source_month={args.source_month}" / "bronze_game.parquet"
    raw_sample_output = (
        output_root
        / "samples"
        / "raw_game_sample"
        / f"source_month={args.source_month}"
        / "raw_game_sample.parquet"
    )
    manifest_output = (
        output_root
        / "bronze"
        / "manifests"
        / f"source_month={args.source_month}"
        / "ingestion_manifest.json"
    )

    write_parquet(bronze_rows, bronze_output, BRONZE_GAME_SCHEMA)
    write_parquet(raw_sample_rows, raw_sample_output, RAW_GAME_SAMPLE_SCHEMA)

    bronze_schema_status, bronze_schema_messages = validate_parquet_schema(
        bronze_output, BRONZE_GAME_SCHEMA, "bronze_game"
    )
    raw_sample_schema_status, raw_sample_schema_messages = validate_parquet_schema(
        raw_sample_output, RAW_GAME_SAMPLE_SCHEMA, "raw_game_sample"
    )
    if "fail" in {bronze_schema_status, raw_sample_schema_status}:
        validation_status = "fail"
    validation_messages.extend(bronze_schema_messages)
    validation_messages.extend(raw_sample_schema_messages)

    manifest = {
        "IngestionRunID": ingestion_run_id,
        "SourceURL": args.source_url,
        "SourceMonth": args.source_month,
        "SourceDataset": args.source_dataset,
        "SourceFileName": source_file_name,
        "DownloadTimestampUTC": download_timestamp_utc,
        "CompressedSizeBytes": input_path.stat().st_size,
        "SourceFileSHA256": source_file_sha256,
        "ParserVersion": PARSER_VERSION,
        "SchemaVersion": SCHEMA_VERSION,
        "GamesParsed": len(bronze_rows),
        "GamesFailed": games_failed,
        "BronzeGameRowsWritten": len(bronze_rows),
        "RawGameSampleRowsWritten": len(raw_sample_rows),
        "BronzeGameOutputPath": str(bronze_output),
        "RawGameSampleOutputPath": str(raw_sample_output),
        "ValidationStatus": validation_status,
        "ValidationMessages": validation_messages,
    }

    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Lichess PGN headers into Bronze game output.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--source-month", required=True)
    parser.add_argument("--source-dataset", default="standard_rated")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--output-root", default=Path("data"), type=Path)
    parser.add_argument("--raw-sample-size", default=10, type=int)
    parser.add_argument("--ingestion-run-id", default=None)
    args = parser.parse_args()

    manifest = ingest(args)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
