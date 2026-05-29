# Rating Dimensions

## Purpose

Define how Lichess ratings should be modeled for game-grain analysis.

This is a classification and dimensional modeling decision, not a metric.

## Modeling Decision

Use separate role-specific rating dimensions for White and Black so Power BI can keep both relationships active.

Do not use average rating in v1.

Do not store rating band text in `fact_game`.

Prefix surrogate key columns with `SK_`, and use matching key names between fact and dimension tables.

## Rationale

Lichess ratings are platform-specific and should not be compared directly to official FIDE, USCF, or other over-the-board ratings.

Within the Lichess population, 200-point rating bands are still analytically useful.

Separate White and Black rating dimensions duplicate a small dimension, but simplify the semantic model and avoid inactive relationship patterns for common report slicing.

## Relationship Pattern

```text
fact_game.WhiteRating_SK -> dim_white_rating.WhiteRating_SK
fact_game.BlackRating_SK -> dim_black_rating.BlackRating_SK
fact_game.RatingDifferenceBucket_SK -> dim_rating_difference_bucket.RatingDifferenceBucket_SK
```

## Fact Columns

Candidate `fact_game` columns:

| Column | Purpose |
|---|---|
| `WhiteRating_SK` | Numeric key for White rating; equals rating value when valid |
| `BlackRating_SK` | Numeric key for Black rating; equals rating value when valid |
| `AbsRatingDifference` | Absolute difference between White and Black ratings |
| `RatingDifferenceBucket_SK` | Bucket key for absolute rating difference |

Example:

| `SourceGameID` | `WhiteRating_SK` | `BlackRating_SK` | `AbsRatingDifference` | `RatingDifferenceBucket_SK` |
|---|---:|---:|---:|---:|
| `j1dkb5dw` | 1639 | 1403 | 236 | 4 |

## `dim_white_rating`

Grain: one row per White rating value.

| Column | Purpose |
|---|---|
| `WhiteRating_SK` | Relationship key; can equal rating value |
| `RatingValue` | Numeric Lichess rating |
| `RatingBand_SK` | Band key |
| `RatingBandLabel` | Display label |
| `MinRating` | Band lower bound |
| `MaxRating` | Band upper bound |
| `SortOrder` | Display sort |

## `dim_black_rating`

Grain: one row per Black rating value.

Same structure as `dim_white_rating`, with `BlackRating_SK` as the relationship key.

## Rating Bands

Use 200-point intervals, with ratings below 800 grouped together.

Initial band pattern:

```text
<800
800-999
1000-1199
1200-1399
...
3200-3399
3400+
Unknown
```

Reason for grouping below 800: very low ratings can include sandbagging, new strong players, provisional behavior, and other volatility that makes fine-grained low-end bands less meaningful.

## Rating Difference Buckets

Use absolute rating difference.

Candidate buckets:

```text
0-49       roughly equal
50-99      small edge
100-199    meaningful edge
200-399    large edge
400-599    very large edge
600+       extreme mismatch
Unknown
```

Chess-domain rationale: in USCF contexts, rating differences of 600+ are commonly understood as extreme mismatches. Lichess ratings are not equivalent to USCF ratings, but `600+` remains a useful Lichess-relative extreme mismatch bucket.

## Future Analysis

Rating growth and sandbagging analysis is a later player-history model, not a v1 `fact_game` metric.

Future candidate fact:

```text
fact_player_rating_event
- Player_SK
- GameDate
- GameSequenceNumber
- RatingAtGame
- RatingDelta
- TimeControl_SK
```

Potential research question:

Can we identify within the first few games whether a player is much stronger than their displayed rating, using openings, performance score, time control, and rating growth behavior?
