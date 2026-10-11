# Iteration 016 - V3 Waterfall Policy

## Goal

Turn the recent blind-recovery experiments into an explicit V3 controller plan.
The key policy question is when to spend fallback cost:

1. use block votes when complete blocks independently recover,
2. use cross-block pooling when localized blocks are weak,
3. use geometry fallback only when localization or timing distress is visible.

## Method

This is a planning model over measured outcomes from iterations 014 and 015.
It does not run new DSP. It records the proposed stage order, the distress
classifier, and the V3 release boundary.

## Current Result

The optimized waterfall accepts fast block votes when the requested vote
threshold is met, then routes localized weak-block cases to pooling before any
geometry search.

| Observation | Vote threshold | Block votes | Pooled RS cost | Decision | Geometry fallback |
| --- | ---: | ---: | ---: | --- | --- |
| `top3_fast_vote` | 2 | 2 | 2 | accept at block vote | no |
| `top5_balanced_vote` | 3 | 3 | 0 | accept at block vote | no |
| `top7_wide_pool` | 3 | 3 | 1 | accept at block vote | no |
| `strict_geometry_spend` | 4 | 3 | n/a | abstain after pooling route | no |
| `zero_vote_pool_recovery` | 2 | 0 | 6 | accept at pooling | no |
| `hypothetical_low_localization` | 2 | 0 | n/a | continue to geometry | yes |

The `zero_vote_pool_recovery` case captures the important app-observed
behavior: pooled recovery can be valid even when no individual block reaches the
standalone vote bar. That is block evidence distress, not geometry distress.

## Interpretation

Proposed V3 stage order:

1. **Pilot window prefilter**: rank likely block windows.
2. **Fast block vote**: accept when independent recovered blocks meet the
   requested vote threshold.
3. **Cross-block pool**: combine carrier scores across localized repeated
   blocks and run one pooled RS recovery.
4. **Geometry fallback**: search timing/crop hypotheses only when localization
   or timing distress is visible.
5. **Max-cost search**: keep broad offline recovery as V3-later support tooling.

V3 should promote repeated 30-second block encoding, pilot-window prefiltering,
two-vote fast acceptance, and cross-block carrier pooling. Broad geometry
fallback, arbitrary crop-length recovery, codec claims, and recorded-audio
claims should remain experimental until separate validation covers them.

Next validation should use separately seeded clean and bounded-crop fixtures,
wrong-secret and unwatermarked controls, and runtime budgets for both
2.5-minute and 5-minute songs.

