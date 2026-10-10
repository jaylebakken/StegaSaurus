# Iteration 003: Joint Pilot-Payload Calibration

## Goal

Test whether local-pilot map selection improves when calibration selects each candidate by its weaker post-round-trip local-pilot and payload margin, rather than by payload margin alone as in iteration 002.

## Method

- Covers: ten seeded, 30-second synthetic music-like variants per profile.
- Transport: 8-byte token, 12 Reed--Solomon parity symbols, four copies, `relative_difference=0.95`, and the `500-3800 Hz` carrier band.
- Profiles: 4 pilot / 12 payload pairs and 8 pilot / 8 payload pairs.
- Calibration: embed each complete candidate rank through the inverse-STFT/STFT round trip, measure signed pilot and payload margins separately, then select the rank maximizing `min(pilot margin, payload margin)`; pilot margin breaks ties.
- Decoder: regenerates two observed candidates per stratum, selects only through the known local pilot, converts ambiguous decisions to erasures, and extracts the payload from disjoint pairs in the selected frame.
- Controls: original unwatermarked cover and watermarked cover decoded with a wrong secret. A control counts only when it exactly returns the known input token.

## Results

| Profile | Exact recovery | Median candidate coverage | Median selected-map accuracy | Median map-erasure rate | Median RS cost | Median SNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 pilot / 12 payload pairs | 0 / 10 | 99.39% | 83.67% | 13.59% | 30 | 41.63 dB |
| 8 pilot / 8 payload pairs | 0 / 10 | 99.25% | 84.34% | 11.21% | 31 | 41.76 dB |

The joint criterion improves median selected-map accuracy by 22.39 percentage points for the small allocation and 18.20 points for the balanced allocation compared with iteration 002. Median RS cost improves from 33 to 30 for the small allocation and remains 31 for the balanced allocation, but both exceed the 12-symbol budget. The small profile has median 32.5 known carrier-bit errors and 3 carrier erasures; the balanced profile has median 34.5 errors and 2 erasures. Both profiles record `0 / 10` exact known-token accepts for unwatermarked and wrong-secret controls.

## Interpretation

- The large map-accuracy improvement confirms the iteration-002 diagnosis: payload-only calibration was incompatible with pilot-guided non-oracle selection.
- Candidate coverage remains near 99%, and the joint criterion reduces local-pilot selection erasures while recovering map accuracy near the iteration-001 consensus baseline.
- Transport still fails because the split-pair payload channel and residual map mistakes leave 14.5 median unknown byte errors, with RS cost more than twice the correction budget.
- This experiment cannot yet separate payload-group damage from residual map-selection damage because both are present in the non-oracle path.

## Decision

Before changing pair allocations, parity, duration, or attacks, run an oracle-map upper-bound study using the exact split-pair encoder profiles. If oracle-map extraction also exceeds the RS budget, the payload pair allocation is insufficient. If it recovers reliably, the remaining priority is stronger local-pilot map selection or additional map redundancy. Do not treat the two zero-control counts as a false-positive-rate estimate.

## Reproduce

The complete machine-readable result for both profiles, all twenty watermarked trials, and their controls is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_003_joint_pilot_payload_calibration.run
```
