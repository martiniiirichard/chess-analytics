from __future__ import annotations

import argparse
import collections
import io
import re
from pathlib import Path
from statistics import mean, median

import chess.pgn
import zstandard


EVAL_PATTERN = re.compile(r"\[%eval\s+([^\]]+)\]")
CLOCK_PATTERN = re.compile(r"\[%clk\s+([^\]]+)\]")


def open_zst_text(path: Path):
    compressed = path.open("rb")
    dctx = zstandard.ZstdDecompressor()
    stream = dctx.stream_reader(compressed)
    return compressed, io.TextIOWrapper(stream, encoding="utf-8", errors="replace")


def classify_time_control(value: str) -> str:
    if not value or value == "-":
        return "unknown"
    if "/" in value:
        return "correspondence"
    base_text, _, inc_text = value.partition("+")
    try:
        base_seconds = int(base_text)
        increment_seconds = int(inc_text or "0")
    except ValueError:
        return "unknown"

    estimated_seconds = base_seconds + (40 * increment_seconds)
    if estimated_seconds < 180:
        return "bullet"
    if estimated_seconds < 480:
        return "blitz"
    if estimated_seconds < 1500:
        return "rapid"
    return "classical"


def percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = round((len(ordered) - 1) * pct)
    return ordered[idx]


def profile_pgn(input_path: Path, output_path: Path, max_games: int | None) -> None:
    result_counts = collections.Counter()
    termination_counts = collections.Counter()
    time_control_counts = collections.Counter()
    time_class_counts = collections.Counter()
    eco_counts = collections.Counter()
    opening_counts = collections.Counter()
    header_nulls = collections.Counter()
    ply_counts: list[int] = []
    eval_games = 0
    clock_games = 0
    eval_nodes = 0
    clock_nodes = 0
    parse_errors = 0
    games = 0

    required_headers = [
        "Event",
        "Site",
        "White",
        "Black",
        "Result",
        "UTCDate",
        "UTCTime",
        "WhiteElo",
        "BlackElo",
        "WhiteRatingDiff",
        "BlackRatingDiff",
        "ECO",
        "Opening",
        "TimeControl",
        "Termination",
    ]

    compressed, text_stream = open_zst_text(input_path)
    with compressed, text_stream:
        while True:
            if max_games is not None and games >= max_games:
                break

            try:
                game = chess.pgn.read_game(text_stream)
            except Exception:
                parse_errors += 1
                continue

            if game is None:
                break

            games += 1
            headers = game.headers
            for header in required_headers:
                if not headers.get(header):
                    header_nulls[header] += 1

            result_counts[headers.get("Result", "missing")] += 1
            termination_counts[headers.get("Termination", "missing")] += 1
            time_control = headers.get("TimeControl", "missing")
            time_control_counts[time_control] += 1
            time_class_counts[classify_time_control(time_control)] += 1
            eco_counts[headers.get("ECO", "missing")] += 1
            opening_counts[headers.get("Opening", "missing")] += 1

            plies = 0
            game_has_eval = False
            game_has_clock = False
            node = game
            while node.variations:
                node = node.variation(0)
                plies += 1
                comment = node.comment or ""
                if EVAL_PATTERN.search(comment):
                    eval_nodes += 1
                    game_has_eval = True
                if CLOCK_PATTERN.search(comment):
                    clock_nodes += 1
                    game_has_clock = True

            if game_has_eval:
                eval_games += 1
            if game_has_clock:
                clock_games += 1
            ply_counts.append(plies)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Lichess PGN EDA: 2013-01 Standard Rated",
        "",
        f"Source file: `{input_path}`",
        f"Games parsed: {games:,}",
        f"Parse errors caught: {parse_errors:,}",
        "",
        "## Grain Implications",
        "",
        f"- Game rows available in this slice: {games:,}",
        f"- Move/ply rows implied by mainlines: {sum(ply_counts):,}",
        f"- Median plies per game: {median(ply_counts):,.0f}" if ply_counts else "- Median plies per game: n/a",
        f"- Average plies per game: {mean(ply_counts):,.1f}" if ply_counts else "- Average plies per game: n/a",
        f"- 95th percentile plies: {percentile(ply_counts, 0.95)}",
        "",
        "## Result Counts",
        "",
        *[f"- `{key}`: {value:,}" for key, value in result_counts.most_common()],
        "",
        "## Time Control Classes",
        "",
        *[f"- `{key}`: {value:,}" for key, value in time_class_counts.most_common()],
        "",
        "## Top Time Controls",
        "",
        *[f"- `{key}`: {value:,}" for key, value in time_control_counts.most_common(15)],
        "",
        "## Top ECO Codes",
        "",
        *[f"- `{key}`: {value:,}" for key, value in eco_counts.most_common(15)],
        "",
        "## Top Openings",
        "",
        *[f"- `{key}`: {value:,}" for key, value in opening_counts.most_common(15)],
        "",
        "## Termination Counts",
        "",
        *[f"- `{key}`: {value:,}" for key, value in termination_counts.most_common()],
        "",
        "## Move Comment Signals",
        "",
        f"- Games with eval comments: {eval_games:,}",
        f"- Move nodes with eval comments: {eval_nodes:,}",
        f"- Games with clock comments: {clock_games:,}",
        f"- Move nodes with clock comments: {clock_nodes:,}",
        "",
        "## Header Missingness",
        "",
        *[f"- `{key}`: {value:,}" for key, value in header_nulls.most_common() if value],
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile a compressed Lichess PGN export.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-games", type=int, default=None)
    args = parser.parse_args()
    profile_pgn(args.input, args.output, args.max_games)


if __name__ == "__main__":
    main()
