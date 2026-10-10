# Iteration 006: Unknown Crop Bound Audit

## Goal

Estimate a feasible early-production maximum for unknown single-edge crop
lengths. This treats "unknown" as a bounded declared search bank rather than an
open-ended discovery problem.

## Method

- Fixed claimed-plan transport path from the blind-recovery track.
- Fresh 30-second synthetic cover: seed `7900`.
- Crop scenarios: leading and trailing crops of `125 ms`, `250 ms`, and
  `500 ms`.
- Candidate policies:
  - `unknown_crop_to_250ms`: `125 ms` grid up to `250 ms`.
  - `unknown_crop_to_500ms`: `125 ms` grid up to `500 ms`.
- The first sweep evaluates watermarked recovery only for all policies.
- Controls are evaluated on the widest policy that recovers every in-bound
  watermarked scenario, using the `250 ms` and maximum-boundary crop cases:
  transformed unwatermarked source and wrong-secret decode.

## Expected Interpretation

The preferred early-production maximum is the widest policy that recovers the
tested in-bound crops without ambiguity or control acceptance, while keeping
attempt counts small enough for an online verifier. This is still bounded
claimed-plan recovery, not arbitrary crop synchronization or unknown-handle
discovery.

## Result

| Policy | Watermarked recoveries | Boundary control acceptances | Median attempts | Maximum attempts |
| --- | ---: | ---: | ---: | ---: |
| `unknown_crop_to_250ms` | 4/6 | n/a | 3 | 3 |
| `unknown_crop_to_500ms` | 6/6 | 0/4 | 3 | 5 |

The `250 ms` policy recovers the `125 ms` and `250 ms` leading/trailing cases
but misses the `500 ms` cases by design. The `500 ms` policy recovers every
tested leading/trailing crop length in the compact grid and keeps transformed
unwatermarked and wrong-secret controls quiet on the `250 ms` and `500 ms`
boundary cases.

## Recommendation

Use `500 ms` as the first early-production maximum for unknown single-edge crop
lengths, with a `125 ms` grid and the existing staged accept/reject/abstain
policy. A verifier should try received duration first, then `125 ms`,
`250 ms`, `375 ms`, and `500 ms` inferred source-duration loss. The current
compact audit does not justify wider default search. A `750 ms+` bank should be
a separate explicit stress mode because runtime grows quickly and the
false-accept surface expands with every added hypothesis.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_006_unknown_crop_bound_audit.run
```
