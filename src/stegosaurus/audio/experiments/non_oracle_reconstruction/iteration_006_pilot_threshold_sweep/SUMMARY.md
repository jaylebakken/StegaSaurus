# Iteration 006: Pilot Threshold Sweep

## Goal

Test whether stricter decoder thresholds can convert marginal local-pilot map decisions into erasures cheaply enough to lower Reed--Solomon damage below the 12-symbol budget.

## Method

- Covers: ten seeded, 30-second synthetic music-like variants.
- Encoder: fixed to iteration 005's contrastive calibration and the leading 4-pilot / 12-payload pair allocation.
- Transport: 8-byte token, 12 Reed--Solomon parity symbols, four copies, `relative_difference=0.95`, and the `500-3800 Hz` carrier band.
- Decoder grid: independently sweep absolute expected-pilot threshold and selected-minus-rival pilot-gap threshold over `0.00`, `0.01`, `0.02`, and `0.04`, producing 16 declared threshold pairs.
- Controls: original unwatermarked cover and watermarked cover decoded with a wrong secret for every threshold pair. A control counts only when it exactly returns the known token.
- Success: exact known-token recovery and byte-level RS cost. Map-selection errors and erasures are reported separately.

## Results

All 16 threshold pairs recover `0 / 10` tokens. Median RS cost ranges from 24.5 to 27, so no pair approaches the 12-symbol correction budget.

| Best in-grid threshold pairs | Exact recovery | Median RS cost | Median selected-map accuracy | Median map-erasure rate | Median known carrier-bit errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| Absolute `0.00`, gap `0.04` | 0 / 10 | 24.5 | 96.996% | 13.59% | 20.5 |
| Absolute `0.01`, gap `0.04` | 0 / 10 | 24.5 | 97.141% | 14.33% | 21.0 |
| Absolute `0.02`, gap `0.04` | 0 / 10 | 24.5 | 97.193% | 14.74% | 21.5 |
| Absolute `0.04`, gap `0.04` | 0 / 10 | 24.5 | 97.240% | 15.90% | 21.5 |

Every threshold pair records `0 / 10` exact known-token acceptances for both unwatermarked and wrong-secret controls. These repeated evaluations share the same ten covers and are not independent false-positive trials.

## Interpretation

- Increasing the declared thresholds slightly improves conditional selected-map accuracy and increases map erasures, but only from roughly 12.4% to 15.9% of physical positions.
- That small erasure increase does not remove enough accepted wrong maps to materially change byte-level RS damage. The best median cost, 24.5, remains more than twice the correction budget.
- The tested threshold range is deliberately bounded and does not demonstrate that no possible threshold can work. It does demonstrate that a blind expansion of the current low range is not justified by recovery results.
- Because the archived records retain aggregate map outcomes but not per-position selected-pilot and rival-pilot scores, the next study must add score-distribution telemetry before choosing wider thresholds.

## Decision

Do not select a production threshold from this grid or extend it to attacks. The next clean study should retain the contrastive encoder and record, for every physical carrier, the selected pilot score, rival pilot score, gap, oracle map correctness, and payload outcome. Use those post-hoc oracle labels only to construct an error-versus-erasure calibration curve; then pre-register a new threshold range and validate it on separate variants before claiming a decoder setting.

## Reproduce

The complete machine-readable result for all 160 thresholded watermarked observations and their declared controls is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_006_pilot_threshold_sweep.run
```
