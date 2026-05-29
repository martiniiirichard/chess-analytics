from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen


ORCHESTRATION_VERSION = "monthly-process-0.1.0"
DEFAULT_BASE_URL = "https://database.lichess.org/standard"


def source_file_name(source_month: str) -> str:
    return f"lichess_db_standard_rated_{source_month}.pgn.zst"


def source_url(source_month: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/{source_file_name(source_month)}"


def raw_input_path(output_root: Path, source_month: str) -> Path:
    return (
        output_root
        / "raw"
        / "lichess"
        / "standard"
        / source_month
        / source_file_name(source_month)
    )


def download_file(url: str, output_path: Path) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    started_at_utc = datetime.now(UTC).isoformat()

    with urlopen(url) as response, output_path.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)

    return {
        "Step": "download",
        "Status": "pass",
        "StartedAtUTC": started_at_utc,
        "CompletedAtUTC": datetime.now(UTC).isoformat(),
        "SourceURL": url,
        "OutputPath": str(output_path),
        "BytesWritten": output_path.stat().st_size,
    }


def extract_json(stdout: str) -> dict[str, Any]:
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"Command did not emit a JSON manifest. Output: {stdout}")
    return json.loads(stdout[start : end + 1])


def run_python_step(step_name: str, command: list[str], cwd: Path) -> dict[str, Any]:
    started_at_utc = datetime.now(UTC).isoformat()
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        return {
            "Step": step_name,
            "Status": "fail",
            "StartedAtUTC": started_at_utc,
            "CompletedAtUTC": datetime.now(UTC).isoformat(),
            "Command": command,
            "ReturnCode": completed.returncode,
            "Stdout": completed.stdout,
            "Stderr": completed.stderr,
        }

    manifest = extract_json(completed.stdout)
    validation_status = manifest.get("ValidationStatus", "unknown")
    return {
        "Step": step_name,
        "Status": validation_status,
        "StartedAtUTC": started_at_utc,
        "CompletedAtUTC": datetime.now(UTC).isoformat(),
        "Command": command,
        "Manifest": manifest,
    }


def assert_step_passed(step_result: dict[str, Any]) -> None:
    if step_result.get("Status") != "pass":
        raise RuntimeError(f"{step_result.get('Step')} failed with status {step_result.get('Status')}.")


def process_month(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path.cwd().resolve()
    output_root = args.output_root.resolve()
    source_month = args.source_month
    run_id = args.orchestration_run_id or str(uuid.uuid4())
    started_at_utc = datetime.now(UTC).isoformat()
    url = source_url(source_month, args.base_url)
    raw_path = raw_input_path(output_root, source_month)

    steps: list[dict[str, Any]] = []

    if raw_path.exists():
        steps.append(
            {
                "Step": "download",
                "Status": "skipped",
                "Reason": "Raw file already exists.",
                "SourceURL": url,
                "OutputPath": str(raw_path),
                "BytesExisting": raw_path.stat().st_size,
            }
        )
    elif args.skip_download:
        steps.append(
            {
                "Step": "download",
                "Status": "skipped",
                "Reason": "--skip-download was provided.",
                "SourceURL": url,
                "OutputPath": str(raw_path),
            }
        )
    else:
        download_result = download_file(url, raw_path)
        steps.append(download_result)
        assert_step_passed(download_result)

    bronze_step = run_python_step(
        "bronze",
        [
            sys.executable,
            "src/data_warehouse/ingestion/ingest_bronze_game.py",
            "--input",
            str(raw_path),
            "--source-month",
            source_month,
            "--source-dataset",
            args.source_dataset,
            "--source-url",
            url,
            "--output-root",
            str(output_root),
        ],
        repo_root,
    )
    steps.append(bronze_step)
    assert_step_passed(bronze_step)

    silver_step = run_python_step(
        "silver",
        [
            sys.executable,
            "src/data_warehouse/transforms/build_silver_game.py",
            "--source-month",
            source_month,
            "--output-root",
            str(output_root),
        ],
        repo_root,
    )
    steps.append(silver_step)
    assert_step_passed(silver_step)

    gold_step = run_python_step(
        "gold",
        [
            sys.executable,
            "src/data_warehouse/transforms/build_gold_game.py",
            "--source-month",
            source_month,
            "--output-root",
            str(output_root),
        ],
        repo_root,
    )
    steps.append(gold_step)
    assert_step_passed(gold_step)

    duckdb_step = run_python_step(
        "duckdb_load",
        [
            sys.executable,
            "src/data_warehouse/load/load_duckdb.py",
            "--source-month",
            source_month,
            "--output-root",
            str(output_root),
        ],
        repo_root,
    )
    steps.append(duckdb_step)
    assert_step_passed(duckdb_step)

    manifest = {
        "OrchestrationRunID": run_id,
        "SourceMonth": source_month,
        "SourceDataset": args.source_dataset,
        "SourceURL": url,
        "RawInputPath": str(raw_path),
        "StartedAtUTC": started_at_utc,
        "CompletedAtUTC": datetime.now(UTC).isoformat(),
        "OrchestrationVersion": ORCHESTRATION_VERSION,
        "ValidationStatus": "pass",
        "Steps": steps,
    }

    manifest_path = output_root / "orchestration" / f"source_month={source_month}" / "monthly_process_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest["ManifestOutputPath"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Process one Lichess source month through the local warehouse pipeline.")
    parser.add_argument("--source-month", required=True)
    parser.add_argument("--output-root", default=Path("data"), type=Path)
    parser.add_argument("--source-dataset", default="standard_rated")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--orchestration-run-id", default=None)
    args = parser.parse_args()

    try:
        manifest = process_month(args)
    except Exception as exc:
        failure_manifest = {
            "SourceMonth": args.source_month,
            "CompletedAtUTC": datetime.now(UTC).isoformat(),
            "OrchestrationVersion": ORCHESTRATION_VERSION,
            "ValidationStatus": "fail",
            "Error": str(exc),
        }
        print(json.dumps(failure_manifest, indent=2))
        raise

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
