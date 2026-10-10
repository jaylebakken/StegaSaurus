# Iteration 007: Embedding Strength Sweep

## Goal

Test whether a stronger spectral pair log-ratio shift improves clean exact-token recovery before changing carrier selection. The token size, 12 Reed--Solomon parity bytes, four-copy layout, seeded variants, and threshold sweep remain fixed.

## Method

- Durations: 30 and 60 seconds.
- Strengths: `relative_difference` of 0.60, 0.72, 0.84, 0.90, and 0.95.
- Trials: ten iteration-six seeded cover variants and virtual timeline offsets per duration and strength.
- Thresholds: `0.010` through `0.070` in `0.010` steps.
- Reliability criterion: exact known-token recovery in all ten trials with no capacity failure.

## Results

No strength and threshold setting met the all-ten-trial reliability criterion. Increasing strength lowered the median Reed--Solomon burden but also lowered embedding SNR.

| Duration | Strength | Best Threshold | Exact Recoveries | Median RS Cost | Median SNR |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 30 s | 0.60 | 0.070 | 0 / 10 | 24.0 | 46.13 dB |
| 30 s | 0.72 | 0.070 | 0 / 10 | 22.0 | 44.56 dB |
| 30 s | 0.84 | 0.050 | 0 / 10 | 20.0 | 43.24 dB |
| 30 s | 0.90 | 0.040 | 0 / 10 | 18.5 | 42.65 dB |
| 30 s | 0.95 | 0.050 | 0 / 10 | 17.0 | 42.19 dB |
| 60 s | 0.60 | 0.070 | 0 / 10 | 23.5 | 49.11 dB |
| 60 s | 0.72 | 0.070 | 0 / 10 | 21.0 | 47.55 dB |
| 60 s | 0.84 | 0.010 | 1 / 10 | 21.5 | 46.23 dB |
| 60 s | 0.90 | 0.040 | 2 / 10 | 17.0 | 45.64 dB |
| 60 s | 0.95 | 0.050 | 3 / 10 | 14.0 | 45.18 dB |

The best observed setting was 60 seconds, `relative_difference=0.95`, and threshold `0.050`. It improved exact recovery from 1/10 at 0.84 to 3/10 and reduced median RS cost from 21.5 to 14.0, but the 12-symbol correction budget was still exceeded too often.

## Decision

- Stronger embedding is a useful diagnostic signal: it improves bit transport, so carrier evidence strength is part of the bottleneck.
- Do not adopt 0.95 as a production setting. It lowers median SNR by about 1 dB relative to 0.84 at 60 seconds and remains far below reliable recovery.
- Do not proceed to compression or DSP attacks. The clean-channel reliability gate remains unsatisfied.

## Next Step

Test carrier selection with the best observed strength, 0.95, while preserving the same seeded variants and exact-token criterion. The selection policy should improve recoverability without merely selecting a favorable single fixture.

## Reproduce

The complete machine-readable output for all 100 trials is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.transport_optimization.iteration_007_embedding_strength_sweep.run
```
