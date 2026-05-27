# Opening Dimensions

## Purpose

Define how ECO codes and Lichess opening names should be modeled for game-grain and opening-performance analysis.

## Modeling Decision

ECO is treated as the stable parent opening classification.

Lichess `Opening` is treated as the authoritative source for observed opening variation labels in this dataset.

External ECO references may enrich `dim_eco`, but should not overwrite Lichess variation names unless a reviewed mapping rule exists.

## Rationale

ECO codes are broadly standardized and useful as compact parent classifications.

Opening variation names are not fully standardized across chess data sources. Lichess, Chess.com, Chessgames, SCID, and other references may label the same line differently.

Because this warehouse is built from Lichess PGN exports, Lichess opening labels are the source-of-record for observed variation names.

## Initial Model

```text
dim_eco -> dim_opening_variation -> fact_game
```

## `dim_eco`

Grain: one row per ECO code.

Candidate columns:

| Column | Purpose |
|---|---|
| `eco_key` | Surrogate key |
| `eco_code` | ECO code such as `C00` |
| `eco_volume` | ECO volume letter, `A` through `E` |
| `parent_opening_name` | Reviewed parent opening name |
| `source_reference` | Source used for enrichment, if any |
| `mapping_status` | `seeded`, `reviewed`, or `enriched` |

## `dim_opening_variation`

Grain: one row per distinct `eco_code` plus Lichess opening name.

Candidate columns:

| Column | Purpose |
|---|---|
| `opening_variation_key` | Surrogate key |
| `eco_key` | Parent ECO key |
| `lichess_opening_name` | Raw opening name from Lichess PGN |
| `normalized_opening_name` | Optional reviewed/cleaned name |
| `mapping_status` | `observed`, `reviewed`, or `overridden` |

## Fact Relationship

`fact_game` should carry `opening_variation_key`.

It should not carry long opening text in Gold.

## Open Questions

- What source should be used to enrich `dim_eco` parent names?
- Should every `A00` through `E99` code be seeded before observation, or only codes observed in Lichess?
- Should `normalized_opening_name` be manually curated, algorithmically cleaned, or left blank until needed?
- What sample-size threshold should opening-performance metrics require?

