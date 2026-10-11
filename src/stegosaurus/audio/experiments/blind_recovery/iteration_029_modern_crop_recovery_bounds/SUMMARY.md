# Iteration 029 - Modern Crop Recovery Bounds

## Goal

Explore whether future StegaSaurus recovery can support arbitrarily truncated
recordings for dense modern pop and rap-style productions. The target audience
is leak attribution for productions with strong bass, drums, and vocals, where
listening checks suggest the current watermark can afford more distortion than
sparse piano, classical, or light jazz material.

## Scope

This iteration measures an oracle geometry upper bound, not a complete blind
decoder. Each selected sample is watermarked once with the current repeated
30-second block profile. The experiment then crops excerpts at several lengths
and positions, keeps only complete original watermark blocks that survive inside
the crop, and verifies pooled evidence from those surviving blocks.

This answers:

```text
If a future blind search can find the surviving block geometry, is there enough
watermark evidence left to recover the attribution?
```

It does not yet answer:

```text
Can the decoder locate those surviving blocks without retained crop geometry?
```

## Measured Results

| Source | Embedded blocks | Minimum recovered crop | Recoverable trials | Notes |
| --- | ---: | ---: | ---: | --- |
| `03. King of Sorrow.wav` | 9 | 120 s | 2 / 24 | Needs multiple surviving block opportunities |
| `08. Gutta Bitch.wav` | 8 | 60 s | 8 / 24 | Best early modern-target signal |
| `10. Cry Me a River.wav` | 10 | 120 s | 1 / 24 | Marginal under current profile |
| `10. Lovers Rock.wav` | 8 | 60 s | 8 / 24 | Best early modern-target signal |
| `19. Get Low.wav` | 11 | 90 s | 7 / 24 | Strong once two or more blocks survive |

All selected tracks embedded with raw input; no whole-song gain preflight was
needed for this subset.

## Interpretation

The current block profile does not support a confident production claim for
arbitrary 15-30 second truncations. Those excerpts often contain no complete
original 30-second block once the crop start is off-grid, and one surviving
block is usually not enough for the pooled Reed-Solomon gate.

The result is still encouraging for the modern-production target. Dense tracks
with strong bass and vocals start recovering once an excerpt contains about two
to three complete surviving block opportunities. In the local samples, the best
cases recovered at 60 seconds, while the weaker modern cases needed 90-120
seconds.

`block_votes` mostly remained zero, so these are still pooled-evidence wins.
That means the future arbitrary-crop decoder should optimize pooled evidence
collection first, then use block votes as a bonus signal when they appear.

## Product Implication

For the current 30-second block design, a conservative early claim would be:

```text
Modern dense productions can be recoverable from unknown excerpts when roughly
60-120 seconds of watermark-bearing material remains, assuming the recovery
pipeline can localize enough surviving block evidence.
```

That is not yet a claim of blind arbitrary-truncation recovery. The next
decoder work should reduce the gap between this oracle upper bound and a
practical blind search.

## Next Iteration

The next logical suite should test a true blind crop-localization controller:

1. Rank candidate windows by pilot response across the cropped recording.
2. Pool the top windows without using oracle crop geometry.
3. Compare watermarked, unwatermarked, and wrong-secret controls.
4. Measure runtime as a function of crop length and stride.
5. Repeat with shorter block profiles, such as 10 or 15 seconds, to see whether
   modern dense tracks can support shorter arbitrary excerpts.

The key question is whether shorter blocks improve crop survivability without
losing too much carrier reliability per block.
