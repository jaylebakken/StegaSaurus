# Iteration 040: Distressed Block Redundancy

This suite tests whether shorter repeated blocks improve the remaining light
recorded-proxy crop failure.

## Method

The suite compared the current 30-second block profile against a 15-second
profile on the remaining hard case:

```text
registry-only parent/child/sibling/unrelated exports
    -> visible child export
    -> 37.25s leading crop, 90s duration
    -> light recorded-proxy distress
    -> current fallback verifier
```

The fallback verifier used a capped consecutive-candidate expansion budget of
10 projected windows. A smaller cap of 6 was faster but only produced a near
miss for the 15-second profile.

The goal was not to prove broad recorded-audio robustness. It was to test
whether more repeated block opportunities inside the same crop can separate the
visible child from parent and sibling records.

## Results

| Block Profile | Best Label | Best RS | Second Label | Second RS | Accepted | Status |
| ---: | --- | ---: | --- | ---: | --- | --- |
| 30s | child | 20 | parent | 20 | none | `child_near_miss` |
| 15s | child | 10 | parent | 20 | child | `pass` |

## Interpretation

The 15-second profile fixes the previously isolated light recorded-proxy crop
case in this deterministic baseline. The visible child remains first, clears
the strict RS budget, and separates from the parent by 10 RS-cost points.

This is the first measured path that passes all four targeted conditions from
iteration 038:

- clean parent crop,
- clean child crop,
- peak-normalized child crop,
- light recorded-proxy child crop.

The tradeoff is runtime and possible capacity/perceptual impact. A 15-second
profile doubles the number of repeated block records for a fixed song duration,
so the application should expose it as a robust/distressed profile rather than
quietly changing every workflow without capacity validation.

## Recommendation

Promote 15-second blocks as the candidate robust crop-plus-distortion profile
for the next product pass, then validate:

1. application workflow tests on the deterministic sample,
2. runtime budget on real samples,
3. capacity and listening checks before making it the default export profile.

