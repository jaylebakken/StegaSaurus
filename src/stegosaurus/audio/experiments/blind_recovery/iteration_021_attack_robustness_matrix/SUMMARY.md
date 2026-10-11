# Iteration 021 - Attack Robustness Matrix

## Goal

Stress the current V3 waterfall against the deferred robustness families:
arbitrary off-grid crop, codec round trip, and recorded-audio-like processing.
The question is whether any family has a safe implementation launching point
using the current sequence of pilot ranking, block evidence, and pooled carrier
recovery.

## Method

- Reuse the held-out repeated-block fixture from iteration 019.
- Apply one named stressor per family:
  - off-grid dual crop: 7.3 seconds leading and 11.7 seconds trailing,
  - MP3 round trip at 96 kbps,
  - light recorded-audio proxy: resample, low-pass, short reverb, 35 dB noise,
    and normalization.
- For each scenario, run:
  - watermarked top-five pooling,
  - unwatermarked top-five control,
  - wrong-secret top-five control.

## Current Result

The matrix finished with two launch candidates and one blocker.

| Scenario | Family | Watermarked | RS cost | Negative controls | Status |
| --- | --- | --- | ---: | --- | --- |
| `off_grid_dual_crop_7p3_11p7` | arbitrary crop | rejected | 36 | rejected at 37 / 35 | blocked |
| `mp3_96k_round_trip` | codec | recovered | 0 | rejected at 32 / 32 | candidate |
| `recorded_audio_proxy_light` | recorded proxy | recovered | 2 | rejected at 35 / 36 | candidate |

## Interpretation

The current waterfall already has a plausible implementation launching point for
named codec and light recorded-audio proxy handling:

- MP3 at 96 kbps recovered cleanly with five token-returning blocks.
- The recorded-audio proxy recovered with pooled RS cost 2 and three
  token-returning blocks.
- In both cases, unwatermarked and wrong-secret controls remained far outside
  the 16-symbol RS budget.

The off-grid crop case is different. The watermarked path rejected with pooled
RS cost 36, nearly indistinguishable from the negative controls. That suggests
the current 15-second ranking grid is not enough for arbitrary crop recovery.
The next question is whether arbitrary crop becomes feasible with a finer
phase/stride bank before pooling, or whether it needs a genuinely new
realignment stage.
