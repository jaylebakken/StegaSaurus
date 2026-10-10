# Iteration 004: Oracle Split-Pair Payload Upper Bound

## Goal

Determine whether the joint-calibrated split-pair payload channel can recover the token when extraction receives the retained exact encoder frame map. This isolates payload-channel damage from non-oracle local-pilot map-selection damage.

## Method

- Covers: ten seeded, 30-second synthetic music-like variants per profile.
- Encoder: unchanged from iteration 003. Each selected frame contains a local-pilot group and a disjoint payload group; calibration maximizes the weaker post-round-trip signed pilot or payload margin.
- Profiles: 4 pilot / 12 payload pairs and 8 pilot / 8 payload pairs.
- Extraction: receive the retained encoder frame map, read payload pairs only, soft-combine four replicas, and apply the same 8-byte, 12-parity-symbol Reed--Solomon transport.
- Scope: this is an oracle upper bound. It does not evaluate non-oracle frame reconstruction, pilot selection, attacks, or false-positive behavior.

## Results

| Profile | Exact recovery | Median / maximum RS cost | Median known bit errors | Median carrier erasures | Median SNR |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 pilot / 12 payload pairs | 10 / 10 | 6.5 / 10 | 4.0 | 0.0 | 41.63 dB |
| 8 pilot / 8 payload pairs | 10 / 10 | 4.5 / 7 | 3.5 | 1.0 | 41.76 dB |

Both profiles remain within the 12-symbol Reed--Solomon correction budget for every named clean trial. The balanced profile has the lower observed RS burden: median 2 unknown byte errors and 1 byte erasure, compared with 3 unknown byte errors and no byte erasures for the small-pilot profile.

## Interpretation

- The split-pair payload channel is sufficient for this clean synthetic fixture when the correct frame map is known.
- Iteration 003's `0 / 10` non-oracle recovery is therefore dominated by frame-map selection, not by an inherently inadequate payload pair allocation, parity budget, or 30-second duration.
- The balanced 8-pilot / 8-payload allocation is the leading candidate for map-selection work because it has the lower retained-map RS cost and slightly higher median SNR in this bounded study.
- This does not establish non-oracle recovery, robustness to transformations, perceptual quality, or a production capacity claim.

## Decision

Keep the token size, RS budget, duration, and split-pair profiles fixed for the next map-selection experiment. Replace iteration 003's per-candidate pilot margin objective with a **contrastive pilot objective**: after embedding a candidate, score the expected pilot at both that candidate and its rival observed frame, then favor the rank with a large selected-minus-rival margin as well as adequate payload evidence. Evaluate clean non-oracle map accuracy before attack conditions.

## Reproduce

The complete machine-readable result for both profiles and all twenty retained-map trials is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_004_oracle_split_pair_upper_bound.run
```
