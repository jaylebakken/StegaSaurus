# Iteration 020 - V3 Release Plan

## Goal

Synthesize the blind-recovery waterfall experiments into a concrete V3 release
boundary. The plan must promote only the pieces supported by measured
experiments and keep expensive geometry/crop behavior behind cautious fallback
language.

## Proposed V3 Waterfall

1. `pilot_window_prefilter`
   - Rank likely 30 second block windows.
   - Stop only after candidate windows are available or no plausible windows
     are found.
2. `fast_block_vote`
   - Decode the best windows independently.
   - Accept early when two independent blocks recover the same handle.
3. `cross_block_evidence_pool`
   - Pool carrier evidence when windows localize plausible blocks but individual
     votes are weak.
   - Accept only when pooled recovery is within RS budget and controls reject.
4. `bounded_crop_support_fallback`
   - Spend high-cost recovery only when cheaper stages fail or edge-crop
     symptoms are present.
   - Report boundary confidence explicitly.
5. `research_geometry_search`
   - Keep broad crop/geometry search in experiments or support tooling until a
     larger validation matrix proves headroom.

## Release Disposition

| Feature | Disposition | Evidence | Gate |
| --- | --- | --- | --- |
| repeated 30s block embedding | promote | iterations 011-013 | application suite plus blind-recovery smoke |
| pilot window prefilter | promote | iteration 012 | plausible block starts rank into candidates |
| fast block vote | promote | iterations 013-014 | two matching recovered blocks |
| cross-block evidence pooling | promote with controls | iterations 015, 018, 019 | wrong-secret and unwatermarked controls reject |
| bounded dual-edge crop recovery | support fallback | iteration 019 | explicit expensive mode; boundary confidence |
| arbitrary crop / codec / recorded audio | defer | not validated | larger held-out attack matrix required |

## V3 Claim Boundary

V3 can claim synthetic repeated-block blind attribution with pilot windowing,
fast block voting, pooled evidence, and explicit negative controls. It should
not claim arbitrary crop, codec, or recorded-audio robustness.

## Next Engineering Step

Implement the product decoder as a staged controller with structured
diagnostics:

- window rankings,
- independent block votes,
- pooled RS cost and erasure/error counts,
- negative-control availability,
- fallback stage reached,
- final confidence class.

The controller should treat `0/5` block votes plus successful pooled recovery as
block evidence distress, not geometry distress, so the expensive geometry
fallback is skipped in that case.
