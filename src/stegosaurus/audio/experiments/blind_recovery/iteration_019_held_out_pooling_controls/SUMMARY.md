# Iteration 019 - Held-Out Pooling Controls

## Goal

Repeat the V3 pooling control gate away from the single fixed fixture used in
iteration 018. The release question is whether cross-block pooling still
separates watermarked evidence from unwatermarked and wrong-secret controls
when the synthetic cover seeds change and the received song has bounded edge
crops.

## Method

- Build held-out five-block synthetic songs from separately seeded covers.
- Evaluate two received-song fixtures in the default smoke gate:
  - clean,
  - 15 second leading plus 15 second trailing crop.
- Rank 30 second windows by pilot evidence every 15 seconds.
- Pool carrier evidence for:
  - top-five watermarked windows,
  - top-five unwatermarked windows,
  - top-five wrong-secret windows.

## Current Result

The default held-out smoke gate passed all six controls.

| Fixture | Control | Expected | Pooled result | Pooled RS cost | Token-returning blocks | Gate |
| --- | --- | --- | --- | ---: | ---: | --- |
| clean | watermarked_top5 | recover | recovered | 0 | 5 | pass |
| clean | unwatermarked_top5 | reject | rejected | 34 | 0 | pass |
| clean | wrong_secret_top5 | reject | rejected | 31 | 0 | pass |
| dual_15s_crop | watermarked_top5 | recover | recovered | 16 | 3 | pass |
| dual_15s_crop | unwatermarked_top5 | reject | rejected | 33 | 0 | pass |
| dual_15s_crop | wrong_secret_top5 | reject | rejected | 37 | 0 | pass |

The run took roughly 30 seconds per fixture for the full control set on the
current machine. The first broader version of this experiment, which attempted
four fixtures plus top-seven overlap pooling everywhere, was stopped after
several minutes because it was too expensive for a routine release gate.

## Interpretation Rules

- Watermarked clean and bounded-crop fixtures should recover within the
  16-symbol Reed-Solomon budget.
- Unwatermarked and wrong-secret controls should reject.
- A watermarked failure in cropped fixtures is a localization or window-coverage
  gap, not proof that pooling is unsafe.
- A negative-control recovery is a release blocker for V3 pooling.

## Interpretation

This strengthens the V3 case for cross-block pooling as the block-distress
fallback before geometry search:

- the held-out clean fixture recovered with zero pooled RS cost,
- the held-out dual-crop fixture recovered, but exactly at the 16-symbol RS
  budget,
- wrong-secret and unwatermarked controls stayed well outside budget,
- bounded crop recovery is feasible but already expensive and near the
  acceptance boundary.

For V3, the production-shaped recommendation remains: promote repeated-block
window ranking, fast block voting, and cross-block pooling; keep broad
geometry/crop search behind an explicit expensive fallback or support workflow
until wider held-out validation proves more headroom.
