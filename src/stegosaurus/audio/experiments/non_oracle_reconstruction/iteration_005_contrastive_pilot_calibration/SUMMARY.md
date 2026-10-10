# Iteration 005: Contrastive Pilot Calibration

## Goal

Improve non-oracle local-pilot map selection by calibrating every candidate against its rival. The encoder selects a candidate only when its post-round-trip payload margin, selected-pilot margin, and selected-minus-rival pilot margin are jointly strong.

## Method

- Covers: ten seeded, 30-second synthetic music-like variants per profile.
- Transport: 8-byte token, 12 Reed--Solomon parity symbols, four copies, `relative_difference=0.95`, and the `500-3800 Hz` carrier band.
- Profiles: 4 pilot / 12 payload pairs and 8 pilot / 8 payload pairs.
- Calibration: probe rank 0 and rank 1 maps separately. For each physical carrier, score its payload at the selected frame, expected pilot at the selected frame, and expected pilot at the rival frame. Select by `min(payload margin, selected pilot margin, selected-minus-rival pilot margin)`.
- Decoder: unchanged from iteration 003. It regenerates two candidates, selects through known pilot evidence only, and emits an erasure for pilot evidence or separation below the configured threshold.
- Controls: original unwatermarked cover and watermarked cover decoded with a wrong secret. A control counts only when it exactly returns the known input token.

## Results

| Profile | Exact recovery | Median candidate coverage | Median selected-map accuracy | Median map-erasure rate | Median RS cost | Median SNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 pilot / 12 payload pairs | 0 / 10 | 99.46% | 96.70% | 13.32% | 26 | 41.67 dB |
| 8 pilot / 8 payload pairs | 0 / 10 | 99.25% | 93.76% | 10.87% | 28.5 | 41.82 dB |

The small-pilot profile improves selected-map accuracy by 13.03 percentage points over iteration 003 and reduces median RS cost from 30 to 26. It still has median 21.5 known carrier-bit errors, 2 carrier erasures, 12.5 unknown byte errors, and 1 byte erasure. Its best observed RS cost is 16, still above the 12-symbol budget. Both profiles record `0 / 10` exact known-token accepts for unwatermarked and wrong-secret controls.

## Interpretation

- Contrastive calibration directly improves the encoder's ability to predict the decoder's two-candidate pilot choice. The small 4-pilot / 12-payload allocation is now the clear leading profile.
- Iteration 004 proves this profile's payload channel recovers `10 / 10` with the exact map, so the remaining failures arise from the small fraction of accepted incorrect map choices rather than payload capacity.
- The decoder currently accepts about 86.7% of physical map positions for the small profile; among accepted positions, 96.7% match the oracle. The remaining accepted errors are expensive because they become unknown data-bit errors rather than declared erasures.
- The zero-control counts remain bounded smoke evidence only, not a false-positive-rate result.

## Decision

Keep the contrastive encoder, 4-pilot / 12-payload allocation, and all transport settings fixed. The next clean experiment should sweep the decoder's local-pilot absolute-score and best-minus-rival thresholds using the same pre-registered trials, report map errors and map erasures separately, and choose a threshold only if it lowers byte-level RS cost below 12 without increasing exact-token false accepts in the declared controls. Do not add attacks until that clean threshold tradeoff is resolved.

## Reproduce

The complete machine-readable result for both profiles, all twenty watermarked trials, and their controls is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run
```
