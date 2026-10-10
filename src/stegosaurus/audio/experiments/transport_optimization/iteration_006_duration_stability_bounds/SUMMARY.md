# Iteration 006: Duration Stability Bounds

## Goal

Test whether iteration 005's smallest verified candidate—an 8-byte token with 12 Reed--Solomon parity bytes, four-copy soft combining, and `relative_difference=0.84`—has a repeatable clean-channel duration or confidence-threshold operating region.

## Method

- Durations: 12, 15, 18, 21, 24, 27, 30, 45, 60, 90, and 120 seconds.
- Thresholds: `0.010` through `0.070` in `0.010` steps.
- Trials: ten deterministic music-like cover variants per duration, each with a distinct seed and virtual source-timeline offset.
- Verification: every result must exactly equal the known embedded 8-byte token. Non-null Reed--Solomon output that differs from the input is a failure.
- Reliability criterion: all ten trials must recover exactly and no trial may lack sufficient eligible frame capacity.
- Scope: clean, oracle-aligned extraction only. This is not an MP3, DSP, crop, time-scale, or real-corpus evaluation.

## Results

No duration and threshold combination met the all-ten-trial reliability criterion. All 110 embeddings had sufficient eligible-frame capacity, so the failures are transport errors rather than simple lack of frame count.

| Duration | Best Threshold | Exact Recoveries | Recovery Rate | Median RS Cost | Max RS Cost | Median SNR |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 12 s | 0.050 | 0 / 10 | 0% | 19.0 | 22 | 39.39 dB |
| 15 s | 0.070 | 0 / 10 | 0% | 18.5 | 23 | 40.40 dB |
| 18 s | 0.040 | 1 / 10 | 10% | 21.0 | 24 | 41.20 dB |
| 21 s | 0.030 | 1 / 10 | 10% | 19.5 | 26 | 41.81 dB |
| 24 s | 0.040 | 1 / 10 | 10% | 16.5 | 26 | 42.60 dB |
| 27 s | 0.060 | 0 / 10 | 0% | 18.0 | 21 | 42.87 dB |
| 30 s | 0.050 | 0 / 10 | 0% | 20.0 | 23 | 43.24 dB |
| 45 s | 0.060 | 0 / 10 | 0% | 20.0 | 23 | 45.04 dB |
| 60 s | 0.010 | 1 / 10 | 10% | 21.5 | 28 | 46.23 dB |
| 90 s | 0.060 | 0 / 10 | 0% | 20.0 | 24 | 47.76 dB |
| 120 s | 0.010 | 1 / 10 | 10% | 18.0 | 28 | 48.99 dB |

The Reed--Solomon parity budget is 12 symbols. Median correction costs of 16.5 to 21.5 exceed that budget, explaining why more duration and higher waveform SNR did not produce reliable recovery. The 30-second exact recovery from iteration 005 was therefore a favorable single-fixture outcome, not an established lower bound.

## Decision

- There is **no observed reliable duration** for the 12-parity configuration in the 12-second to 120-second range under this ten-variant clean study.
- Do not declare 30 seconds a production minimum and do not proceed to MP3 or DSP attribution experiments with this transport.
- Capacity is not the current blocker: every trial could map all 184 logical carrier bits into each four-copy plan. The per-frame carrier quality and resulting byte error/erasure rate are the blockers.
- Increasing clip duration alone is not a valid remedy. It raises SNR in this fixture family but does not lower RS cost below the correction budget consistently.

## Next Step

Iteration 007 should improve the carrier before revisiting duration: add adaptive high-energy frame selection with interleaved replica placement, or test a stronger within-frame differential carrier. Keep exact-token verification, seeded cover variants, byte-level RS accounting, and the all-trials reliability criterion. Only test transformations after a clean variant study shows stable recovery.

## Reproduce

The complete machine-readable output for all 110 clean trials is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.transport_optimization.iteration_006_duration_stability_bounds.run
```
