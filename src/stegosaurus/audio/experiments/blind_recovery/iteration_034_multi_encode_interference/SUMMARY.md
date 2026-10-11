# Iteration 034 - Multi-Encode Interference

## Goal

Start the V4.x crop-plus-distress optimization track by identifying an obvious
capacity bottleneck: what happens if the same song is encoded more than once?

The motivating question was whether adding more watermarks could help arbitrary
crops survive by giving the decoder more chances. This iteration tests the
dangerous version first: stacking independent export handles onto the same
waveform.

## Method

Using `10. Lovers Rock.wav`, the experiment repeatedly embedded independent
handles into the output of the previous embed:

```text
source -> handle 0
       -> handle 1
       -> handle 2
       -> ...
```

For each stack count, every retained record was verified against the final
stacked waveform.

Tested stack counts:

```text
1, 2, 3, 4, 6, 8
```

This is a clean retained-record test. It does not include crop localization,
distress transforms, or recorded-audio proxies yet.

## Results

| Stack count | Recovered handles | Best handle index | Minimum RS cost | Median RS cost | Wrong recovered handles |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 0 | 4 | 4.0 | 0 |
| 2 | 0 | 0 | 21 | 23.0 | 0 |
| 3 | 0 | 0 | 17 | 31.0 | 0 |
| 4 | 0 | 0 | 22 | 28.5 | 0 |
| 6 | 0 | 5 | 28 | 31.0 | 0 |
| 8 | 0 | 4 | 29 | 30.5 | 0 |

The single encode recovered cleanly with pooled RS cost 4. After a second
independent encode, both handles failed the current RS budget. Larger stack
counts stayed unrecoverable.

No wrong watermark was accepted in this clean retained-record test. The failure
mode was capacity collapse, not false attribution.

## Interpretation

Independent stacked watermarks are not a good path toward crop-plus-distress
robustness. They damage carrier evidence enough that clean retained-record
verification fails before any crop or distress is applied.

This supports the suspicion that crops reduce capacity sharply: if a second
full-song independent watermark is already too much, then relying on multiple
different overlaid handles to survive arbitrary excerpts is likely worse.

The next direction should avoid independent-handle stacking and instead test:

```text
same-handle redundancy
shorter independently recoverable blocks
block-level repetition schedules
distortion-tolerant source localization
gain-normalized carrier scoring
```

## Bottleneck Identified

The main limiting factor is carrier-evidence budget. The current carrier plan
does not have enough margin for independent overlays. Pooling cannot repair the
damage once each retained handle's symbol cost rises above the RS budget.

## Next Experiment

Iteration 035 should test **same-handle repetition strategies** rather than
independent-handle stacking:

1. Encode the same handle into shorter repeated regions.
2. Compare 30s, 20s, 15s, and 10s block profiles on modern dense samples.
3. Crop off-grid excerpts and measure how many usable same-handle blocks survive.
4. Apply peak normalization after crop to isolate carrier scoring sensitivity.

The goal is to recover from crop-plus-light-distress by increasing same-claim
evidence opportunities, not by layering different claims on top of each other.
