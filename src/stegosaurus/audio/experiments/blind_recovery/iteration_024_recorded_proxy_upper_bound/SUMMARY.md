# Iteration 024 - Recorded Proxy Upper Bound

## Goal

Sweep multiple levels of synthetic recorded-audio proxy distortion, identify
the strongest level recovered by the current waterfall while controls reject,
and write a WAV example for listening validation.

## Method

Each level applies:

- resample down and back,
- low-pass filtering,
- deterministic synthetic room response,
- deterministic white noise,
- peak normalization.

The current waterfall is unchanged: rank windows, recover block evidence, pool
top-five carrier evidence, and require unwatermarked plus wrong-secret controls
to reject.

## Current Result

The strongest recovered level was `level_2_moderate`.

| Level | Recovered | Watermarked RS cost | Token-returning blocks | Unwatermarked RS cost | Wrong-secret RS cost |
| --- | --- | ---: | ---: | ---: | ---: |
| `level_1_light` | yes | 2 | 3 | 35 | 36 |
| `level_2_moderate` | yes | 8 | 0 | 34 | 36 |
| `level_3_strong` | no | 34 | 0 | 38 | 35 |
| `level_4_heavy` | no | 38 | 0 | 37 | 36 |
| `level_5_extreme` | no | 36 | 0 | 37 | 36 |

The highest recovered artifact was written to:

```text
src/stegosaurus/audio/experiments/blind_recovery/iteration_024_recorded_proxy_upper_bound/level_2_moderate_recovered_example.wav
```

## Upper-Bound Profile

`level_2_moderate` applies:

- resample to 10 kHz and back,
- low-pass at 3.4 kHz,
- 120 ms synthetic room decay,
- 16% room mix,
- 30 dB white-noise SNR,
- peak normalization to 0.82.

## Interpretation

`level_2_moderate` is the current measured upper bound for this deterministic
recorded-audio proxy ladder. It recovered with pooled RS cost 8 while both
negative controls remained outside the 16-symbol budget.

The result is also a useful waterfall signal: `level_2_moderate` had zero
individual token-returning blocks, so the recovery came entirely from pooled
carrier evidence. That makes it a block-distress case, not a geometry-distress
case.

`level_3_strong` and above are currently unworkable with this waterfall. Their
watermarked RS costs are in the same range as the negative controls.
