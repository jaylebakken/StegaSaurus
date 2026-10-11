# Iteration 023 - Robustness Launch Plan

## Goal

Convert the robustness experiments into a clear implementation launching point
or blocker for each deferred family: arbitrary crop, codec, and recorded-audio
processing.

## Family Disposition

| Family | Disposition | Evidence | Launch Point |
| --- | --- | --- | --- |
| MP3 96k codec | launch candidate | iteration 021 recovered at RS cost 0; controls rejected at 32 / 32 | named codec profile around current waterfall |
| light recorded-audio proxy | launch candidate | iteration 021 recovered at RS cost 2; controls rejected at 35 / 36 | named recorded-proxy profile around current waterfall |
| arbitrary off-grid crop | blocked; needs new stage | iteration 021 failed at RS cost 36; iteration 022 phase bank failed at RS cost 33 | crop synchronization before pooling |

## Implementation Sequence

1. Add robustness diagnostics to the verifier result:
   - ranked windows,
   - block votes,
   - pooled RS cost,
   - controls run or omitted,
   - waterfall stage reached.
2. Implement named codec and recorded-proxy profiles using the current
   prefilter, block vote, and pooling waterfall.
3. Keep arbitrary crop experimental and prototype a new synchronization stage:
   - crop-offset estimation,
   - local block-boundary refinement,
   - soft pooling across small offset neighborhoods.
4. Promote crop only after near-start windows rank into the candidate set and
   wrong-secret/unwatermarked controls reject with RS headroom.

## Claim Boundary

The launchable features are named codec and light recorded-audio proxy handling
under measured profiles. Arbitrary crop is not launchable through the current
waterfall plus larger search alone; it needs a synchronization stage before it
is suitable for product implementation.
