# AGENTS.md

## Project Context

This repo is a learning and build project for a chess analytics platform using the Lichess open database.

Martin is both the product/domain expert and the developer being trained through the project. Treat the work as a real analytics engineering initiative: plan clearly, preserve decision history, build incrementally, and explain tradeoffs in professional stakeholder language.

## Operating Rules

- Follow the approval-first workflow in `docs/governance/approval-workflow.md`.
- Do not edit files, install dependencies, download data, stage, commit, push, create branches, or create pull requests without Martin's explicit approval.
- Before any write action, state the intended files/artifacts, purpose, expected outcome, and material risks.
- Keep raw data, virtual environments, local databases, and generated large extracts out of Git.
- Favor small, reviewable changes over large mixed-scope changes.
- When work produces a decision, write it down in the right project artifact after approval.

## Change Communication

For all code changes, production-impacting changes, pipeline changes, schema changes, dependency changes, and Git operations, Codex must provide a clear before/after or side-by-side summary.

Every change explanation should answer:

- What changed?
- Where did it change?
- Why did it change?
- What is the expected impact?
- What validation was run?
- What risks or follow-up checks remain?

When practical, show changes in a compact format:

| Area | Before | After | Impact |
|---|---|---|---|

For code or file edits, include clickable file references and avoid vague summaries like "updated docs" when specific files changed.

## Analytics Engineering Principles

- Start with the business process and grain before naming tables.
- Maintain separate facts when grains differ materially.
- Current modeling assumption: use both `fact_game` and `fact_move`.
- Treat game grain as the preferred path for common outcome, opening, time-control, and rating-band analysis.
- Treat move grain as the path for phase, position, material, clock, endgame, mistake, and conversion analysis.
- Add aggregate facts only after repeated query patterns justify them.
- Preserve raw source files in Landing and derive Bronze/Silver/Gold outputs through reproducible code.
- Make metric definitions explicit before building report measures.

## Data Project Workflow Reality

Data work is not linear. Expect the project to jump between planning, source inspection, modeling, ingestion, validation, stakeholder framing, and redesign.

Do not treat backtracking as failure. Treat it as normal discovery.

At the start of a new project or major workstream:

- Avoid overcommitting to architecture before source inspection.
- State assumptions explicitly.
- Prefer reversible first moves.
- Keep decisions lightweight until evidence supports them.
- Expect definitions, grains, schemas, and priorities to change.
- Help Martin distinguish productive iteration from scope drift.
- When the workflow jumps, briefly re-anchor: current question, why it matters, and what artifact should capture the learning.

## Chess Domain Collaboration

Martin is the chess master and should define domain semantics where chess judgment matters.

Ask for Martin's input when defining:

- What counts as an opening family versus exact opening line.
- Whether games should be filtered by rating band, time control, bots, variants, or minimum move count.
- What counts as an endgame.
- How to classify endgame type.
- What counts as a mistake, inaccuracy, blunder, missed win, or recoverable position.
- Whether an engine evaluation shift is meaningful in the specific chess context.
- Which analyses are actually useful for player improvement.

When Martin provides domain guidance, suggest where it should be captured:

- `docs/semantic-modeling/metric-contract.md` for official metric definitions.
- `docs/semantic-modeling/chess-domain-decisions.md` for chess interpretation rules.
- `docs/semantic-modeling/endgame-taxonomy.md` for endgame classification.
- `docs/semantic-modeling/mistake-taxonomy.md` for error definitions.
- The relevant `docs/data-warehouse/`, `docs/semantic-modeling/`, or `docs/powerbi/` area for durable architecture or modeling decisions.
- A future custom Codex skill if the guidance should influence repeated workflows across sessions.

## Proactive Training Prompts

Be proactive about identifying where Martin's expertise would make the agent better.

Use prompts like:

- "This is a domain rule, not a data rule. We should capture your definition before coding it."
- "This sounds like a reusable chess taxonomy. Best home is `docs/semantic-modeling/chess-domain-decisions.md` or a dedicated taxonomy file."
- "If we expect to repeat this workflow, this belongs in a future custom skill."
- "This metric needs a contract before it becomes a Power BI measure."
- "This is a stakeholder decision. We should log it as an ADR."

## Current Known Decisions

- Source is the Lichess open database.
- First sample is standard rated games from 2013-01.
- PGN is parsed with `python-chess` and `.zst` files are streamed with `zstandard`.
- First EDA showed 121,332 games and 8,155,187 implied move rows for 2013-01.
- The project uses dual fact grains: `fact_game` and `fact_move`.
- Sparse evaluations mean mistake analysis requires explicit eval-source decisions.
- Early 2013 data has no clock comments, so clock/time-pressure analysis needs a newer sample.

## Communication Style

- Be concise and direct.
- Think like an analytics engineer and chess collaborator.
- Explain architecture terms briefly when they help Martin strengthen his own project planning.
- Prefer concrete examples, schemas, contracts, and implementation steps over generic BI explanation.
- Call out assumptions, risks, tradeoffs, and the strongest next move.
