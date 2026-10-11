# Iteration 018 - Pooling Control Gate

## Goal

Validate the first release gate for promoting cross-block carrier pooling into
the V3 core: watermarked pooling should recover, wrong-secret and unwatermarked
controls should reject, and adding overlapping non-block windows should not
destabilize the pooled result.

## Method

- Reuse the five-block synthetic song and top-seven pilot ranking from
  iteration 015.
- Pool the top five exact-looking watermarked windows.
- Pool the top seven windows, including the two overlapping non-block windows.
- Pool the same ranked windows from an unwatermarked source song.
- Pool the watermarked song with a wrong-secret carrier plan.

## Current Result

All four control scenarios matched their expected outcome.

| Scenario | Expected | Pooled result | Pooled RS cost | Token-returning blocks | Gate |
| --- | --- | --- | ---: | ---: | --- |
| `watermarked_top5` | recover | recovered | 0 | 5 | pass |
| `watermarked_top7_with_overlaps` | recover | recovered | 1 | 5 | pass |
| `unwatermarked_top5` | reject | rejected | 36 | 0 | pass |
| `wrong_secret_top5` | reject | rejected | 34 | 0 | pass |

The top-seven ablation included two overlapping non-block windows. Pooling still
recovered with only one pooled erasure and no pooled symbol errors.

## Interpretation

This clears the first V3 pooling control gate on the current synthetic fixture:

- pooled watermarked evidence recovers cleanly,
- unwatermarked pooled evidence remains far outside the 16-symbol RS budget,
- wrong-secret pooled evidence remains far outside the 16-symbol RS budget,
- adding the two highest-ranked overlapping non-block windows does not
  destabilize the pooled result.

This is still not a full release claim. The next required validation is a
separately seeded held-out run that repeats these controls across multiple
synthetic songs, including bounded crop cases where localization remains
plausible but individual block votes are weak.

