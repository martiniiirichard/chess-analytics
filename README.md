# Chess Analytics Platform

Working project for analyzing the Lichess open database from raw PGN exports through an on-prem analytical warehouse and, later, Power BI/Fabric.

Primary source: https://database.lichess.org/

## Current Direction

- Start with standard rated games.
- Use the earliest month, 2013-01, as the first EDA slice.
- Preserve raw PGN files in a landing zone.
- Parse into structured facts at both game grain and move grain.
- Use EDA to decide which advanced facts are worth building before scaling to larger months.

## Repo Areas

- `docs/`: planning, architecture notes, metric definitions, project status.
- `data/`: local raw/sample data only; should not be committed.
- `notebooks/`: optional EDA notebooks.
- `src/`: ingestion, parsing, profiling, and transformation code.
- `sql/`: warehouse DDL and load scripts.
- `powerbi/`: future Power BI model/report artifacts.

