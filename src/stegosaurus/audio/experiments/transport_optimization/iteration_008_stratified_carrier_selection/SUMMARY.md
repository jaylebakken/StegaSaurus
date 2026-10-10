# Iteration 008: Stratified Carrier Selection

## Goal

Compare iteration 007's sequential first-eligible-frame mapping with a stratified high-energy policy. The new policy chooses the strongest secret-pair-eligible frame in each ordered time stratum, preserving four-copy temporal distribution while avoiding an early-frame selection bias.

## Method

- Fixed transport: 8-byte token, 12 Reed--Solomon parity bytes, four-copy layout, and `relative_difference=0.95`.
- Durations: 30 and 60 seconds.
- Policies: baseline `sequential` and `stratified_pair_energy`.
- Trials: ten seeded cover variants and virtual timeline offsets per duration and policy.
- Thresholds: `0.010` through `0.070` in `0.010` steps.
- Reliability criterion: exact input-token recovery in all ten trials with no capacity failure.

## Results

Neither policy met the reliability criterion. The energy policy helped the 30-second case slightly but degraded the best 60-second result.

| Duration | Policy | Best Threshold | Exact Recoveries | Median RS Cost | Median SNR |
| ---: | --- | ---: | ---: | ---: | ---: |
| 30 s | Sequential | 0.050 | 0 / 10 | 17.0 | 42.19 dB |
| 30 s | Stratified pair energy | 0.050 | 2 / 10 | 16.5 | 41.35 dB |
| 60 s | Sequential | 0.050 | 3 / 10 | 14.0 | 45.18 dB |
| 60 s | Stratified pair energy | 0.010 | 2 / 10 | 22.0 | 43.47 dB |

All settings had sufficient frame capacity. The mixed outcome indicates that raw pre-embedding pair energy alone is not a stable proxy for the post-inverse-STFT extraction score. The selected-frame map remains oracle supplied, so this result also does not solve independent decoder synchronization.

## Decision

- Do not integrate the stratified pair-energy policy. It is not a consistent improvement over sequential selection.
- Keep 0.95 only as an experiment parameter, not a product configuration.
- Carrier selection remains a promising direction, but it needs a predictor tied to actual post-round-trip decision margin rather than raw pair energy.

## Next Step

Investigate a calibrated carrier-quality metric: estimate each candidate frame's post-embed/post-inverse-STFT signed-score margin, then select distributed frames above a pre-registered margin floor. Validate that metric on held-out seeded variants before using it for token transport.

## Reproduce

The complete machine-readable output for all 40 trials is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.transport_optimization.iteration_008_stratified_carrier_selection.run
```
