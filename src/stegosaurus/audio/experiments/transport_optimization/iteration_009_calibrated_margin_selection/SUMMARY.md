# Iteration 009: Calibrated Post-Round-Trip Margin Selection

## Goal

Test whether a carrier selector based on actual internal reconstruction behavior can reduce token transport damage. The selector evaluates two raw-energy-qualified candidate frames in every time stratum through complete embed, inverse-STFT, and re-STFT probe passes; it selects the candidate with the stronger expected-bit signed extraction margin.

## Method

- Fixed transport: 8-byte token, 12 Reed--Solomon parity bytes, four-copy layout, and `relative_difference=0.95`.
- Durations: 30 and 60 seconds.
- Policies: iteration 007's `sequential` baseline and `calibrated_round_trip_margin`.
- Calibration: two complete probe watermarks per cover, one for each ranked raw-energy candidate. The final frame map combines the highest measured signed margin from each stratum.
- Trials: ten seeded cover variants and virtual timeline offsets per duration and policy.
- Thresholds: `0.010` through `0.070` in `0.010` steps.
- Reliability criterion: exact known-token recovery in every trial without capacity failure.

## Results

The calibrated selector met the clean reliability criterion for both tested durations and every tested threshold. The sequential baseline did not.

| Duration | Policy | Best Threshold | Exact Recoveries | Median RS Cost | Maximum RS Cost | Median SNR |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 30 s | Sequential | 0.050 | 0 / 10 | 17.0 | 20 | 42.19 dB |
| 30 s | Calibrated margin | 0.010 | 10 / 10 | 0.0 | 2 | 42.26 dB |
| 60 s | Sequential | 0.050 | 3 / 10 | 14.0 | 19 | 45.18 dB |
| 60 s | Calibrated margin | 0.010 | 10 / 10 | 0.0 | 2 | 44.28 dB |

At both 30 and 60 seconds, all thresholds from `0.010` through `0.070` achieved 10/10 exact recoveries with the calibrated policy. The selector reduced the 60-second median RS cost from 14 to 0 while reducing median embedding SNR by about 0.9 dB.

## Interpretation Boundaries

- This demonstrates a clean **encoder-side carrier-quality** improvement in the tested synthetic variant family.
- It is still oracle aligned: the extractor receives the source frame map. The selector does not yet let an independent decoder reconstruct the selected carrier locations after edits.
- The calibration cost is three complete STFT passes through the cover path per output: two probes plus the final watermark. This is practical only as an experimental encoder-side quality step until optimized.
- The probes and final extraction share the same transform model. The result does not establish MP3, DSP, crop, resampling, time-scale, perceptual, or real-corpus robustness.

## Decision

- Keep calibrated post-round-trip margin as the leading clean-channel carrier-selection candidate.
- The clean variant gate is now satisfied for this bounded test, so the next experiment may measure named transformations while retaining oracle alignment and exact-token verification.
- Before any production claim, validate on a held-out corpus and design deterministic decoder-side map recovery or local candidate scanning.

## Next Step

Run a pre-registered transformation study using the calibrated selector: clean PCM, MP3 at named bitrates, resampling, normalization, noise, low-pass filtering, and bounded crops. Report exact-token recovery, byte-level RS damage, SNR, and the oracle-mapping limitation separately for every attack.

## Reproduce

The complete machine-readable output for all 40 trials is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.transport_optimization.iteration_009_calibrated_margin_selection.run
```
