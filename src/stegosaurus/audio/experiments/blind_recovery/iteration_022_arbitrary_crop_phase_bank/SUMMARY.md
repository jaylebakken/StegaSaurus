# Iteration 022 - Arbitrary Crop Phase Bank

## Goal

Test whether the off-grid crop failure from iteration 021 is merely a coarse
window-grid problem. This keeps the current waterfall intact but replaces the
15 second ranking grid with a 2.5 second phase bank before pooling.

## Method

- Reuse the held-out fixture from iteration 019.
- Apply the same off-grid crop as iteration 021:
  - 7.3 seconds leading crop,
  - 11.7 seconds trailing crop.
- Rank 30 second candidate windows every 2.5 seconds.
- Pool top-five evidence for:
  - watermarked audio,
  - unwatermarked control,
  - wrong-secret control.

## Current Result

The 2.5 second phase bank did not rescue the off-grid crop.

| Control | Expected | Pooled result | Pooled RS cost | Near starts in top five | Gate |
| --- | --- | --- | ---: | ---: | --- |
| watermarked_top | recover | rejected | 33 | 0 | fail |
| unwatermarked_top | reject | rejected | 34 | 0 | pass |
| wrong_secret_top | reject | rejected | 33 | 0 | pass |

The phase bank ranked 41 candidate windows and spent roughly 8.5 seconds in
prefiltering plus 27.2 seconds in extraction on the current machine. None of
the top-five windows were within the 300 ms near-start tolerance.

## Interpretation

The arbitrary crop failure is not just a coarse 15 second stride problem. A
2.5 second phase bank still ranked the wrong windows and left the watermarked
pooled RS cost indistinguishable from the negative controls.

That makes arbitrary crop unworkable as a simple extension of the current
waterfall. The implementation launching point should be a new synchronization
stage, not merely a larger top-K or finer phase bank. Candidate directions:

- pilot-energy timeline scan that estimates crop offset before carrier
  extraction,
- local block-boundary refinement around high-pilot windows,
- soft pooling across small offset neighborhoods instead of one hard window
  per ranked candidate,
- explicit abstention when ranked windows do not include near-start evidence.
