# Iteration 039: Distressed Handle Calibration

This suite tests whether export handle selection can separate the remaining
light recorded-proxy crop failure from iteration 038.

## Method

Each trial created a registry-only chain with:

- one parent export
- one visible child export
- one sibling child export
- one unrelated control export

The visible child export was cropped at 37.25 seconds for 90 seconds, then
passed through the named light recorded-proxy transform. Verification used the
current fallback workflow from iteration 038.

## Results

| Trial | Best label | Best RS | Second label | Second RS | Gap | Status |
| ---: | --- | ---: | --- | ---: | ---: | --- |
| 0 | child | 20 | parent | 20 | 0 | `ambiguous_child_evidence` |
| 1 | child | 20 | parent | 20 | 0 | `ambiguous_child_evidence` |

The child ranked first in both trials, but the RS-cost gap was zero. No trial
produced a uniquely accepted child.

## Interpretation

Handle choice alone did not separate the light recorded-proxy failure. The
distressed signal carries enough information to keep the visible child near the
top, but not enough discriminating evidence to safely distinguish it from the
parent under the current carrier and scoring scheme.

## Recommendation

Do not solve this by relaxing acceptance or by issuing different-looking
handles alone. The next hardening step needs better carrier/evidence quality:

- stronger or more redundant block evidence,
- a distress-aware carrier scoring path,
- or a product state that reports this class as `inconclusive_distressed_match`
  rather than accepting a risky attribution.

