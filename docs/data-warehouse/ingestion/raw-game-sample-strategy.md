# Raw Game Sample Strategy

## Purpose

The `raw_game_sample` table preserves a tiny forensic sample of raw PGN text from each monthly Lichess export before the downloaded source file is deleted.

This supports:

- Parser debugging after raw monthly files are removed.
- Human inspection of real PGN structure.
- Regression testing against known source examples.
- Evidence that a specific monthly file was processed.
- Teaching and documentation without retaining large raw files.

This table is not intended for analytics, reporting, or statistical sampling.

## Context

The full standard rated Lichess database is too large to retain comfortably on a laptop. The working ingestion pattern is:

1. Download one monthly `.pgn.zst` file.
2. Compute source metadata and hash.
3. Extract a small number of raw PGNs into `raw_game_sample`.
4. Stream-parse the full file into Bronze outputs without persisting full FEN.
5. Validate row counts and parse quality.
6. Delete the downloaded monthly `.pgn.zst` file after successful validation.

Raw PGN does not contain FEN for every move. FEN becomes large only if generated and stored during parsing. The no-FEN policy applies to parsed Bronze/Silver move outputs, not to raw PGN itself.

## Grain

One row represents one raw PGN game captured from one source monthly export.

The initial policy is to capture the first `10` parseable games per monthly file.

Reason: this is fast, deterministic, easy to explain, and sufficient for parser/debug evidence. It is intentionally not a statistically representative sample.

## Candidate Schema

| Column | Type | Notes |
|---|---|---|
| `source_month` | string | Month represented by the Lichess export, such as `2013-01` |
| `source_dataset` | string | Example: `standard_rated` |
| `sample_rank` | integer | 1 through N within the monthly file |
| `game_id` | string | Derived from the Lichess site URL when available |
| `raw_pgn_text` | string | Complete raw PGN text for the sampled game |
| `source_url` | string | Monthly source URL |
| `source_file_name` | string | Downloaded file name |
| `source_file_sha256` | string | SHA256 of compressed source file |
| `compressed_size_bytes` | bigint | Size of downloaded `.pgn.zst` file |
| `parser_version` | string | Version of local parser code/config |
| `captured_at_utc` | timestamp | When the sample row was captured |
| `ingestion_run_id` | string | Run identifier linking sample to manifest and Bronze outputs |

## Storage Policy

- Keep `raw_game_sample` small and durable.
- Keep the full downloaded monthly `.pgn.zst` only until Bronze outputs and validation artifacts are complete.
- Do not store generated per-ply FEN in `raw_game_sample`.
- Do not use `raw_game_sample` as the source for analytics.
- Store `raw_game_sample` in the same local warehouse/database as ingestion manifests once the warehouse exists.

## Raw File Deletion Rule

No manual approval is needed to delete the downloaded monthly raw file when all required ingestion steps completed successfully:

- Monthly Bronze ingestion completed.
- Required validation checks passed.
- Ingestion manifest was written.
- Raw game sample was captured.
- No required step was skipped.

If any required step fails or is skipped, raw file deletion must pause and Martin must approve the next action.

## Validation Role

`raw_game_sample` should be used with an ingestion manifest.

The manifest should capture:

- Source URL
- Source month
- Source file name
- Download timestamp
- Compressed size in bytes
- SHA256 hash
- Games parsed
- Games failed
- Move rows written
- Bronze output paths
- Bronze output sizes
- Parser version
- Schema version
- Validation status

Together, the manifest and raw sample provide enough evidence to troubleshoot most parser issues without retaining the full raw monthly file.

## Ingestion Sequence

```text
download_monthly_file
compute_sha256
capture_first_10_raw_pgns
stream_parse_to_bronze_game
stream_parse_to_bronze_move_no_fen
write_ingestion_manifest
run_validation_checks
delete_raw_file_if_validation_passes
```

## Validation Checks

Minimum checks before deleting the monthly raw file:

- Source file exists and SHA256 was computed.
- At least `10` raw sample games were captured, unless the file has fewer than 10 games.
- Game count is greater than zero.
- Move row count is greater than game count.
- Parse failure rate is below the agreed threshold.
- Bronze game and move outputs exist.
- Ingestion manifest was written.

Future checks:

- Result distribution sanity check.
- Time-control distribution sanity check.
- ECO/opening missingness check.
- Deterministic re-parse of `raw_game_sample` rows.
- Reconciliation between sampled PGN headers and Bronze game rows.

## Open Decisions

- Should the sample always be first 10 games, or first 10 plus 10 deterministic hash-selected games?
- Should failed/unparseable games be captured in a separate `raw_parse_failure_sample` table?
- Should raw samples be stored as database rows, Parquet, or plain `.pgn` files during the laptop prototype?
- What parse failure rate is acceptable before retaining the raw file for investigation?

## Current Recommendation

Start with first `10` raw PGNs per monthly file and store them in a durable `raw_game_sample` artifact.

Do not solve representativeness yet. This table is for traceability and debugging. Analytical sampling should be a separate design.

