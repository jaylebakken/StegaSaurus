# Iteration 015 - Cross-Block Evidence Pooling

## Goal

Research the block-distress fallback implied by iterations 013 and 014. Instead
of spending geometry search on high-pilot block failures, pool repeated block
carrier evidence by carrier position and run one Reed--Solomon recovery over the
pooled observation.

## Method

- Fixture: same 2.5-minute synthetic song with five independent 30-second
  watermarked blocks.
- Rank the top seven 30-second windows with the pilot prefilter.
- Reconstruct each ranked window with received-duration edge-mode decoding.
- Retain each block's combined carrier scores whether or not the block recovers.
- Pool top-3, top-5, and top-7 carrier scores with absolute-score weighting.
- Threshold pooled carrier scores at the existing `0.01` confidence gate and run
  one RS recovery.

## Current Result

The evidence-pooling path recovered the handle for every pooled set. The
important change is the pooled RS burden:

| Pool | Exact starts | Blocks returning token | Pooled bit errors | Pooled erasures | Pooled RS cost | Recovered |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| top 3 | 3 | 3 | 1 | 0 | 2 | yes |
| top 5 | 5 | 5 | 0 | 0 | 0 | yes |
| top 7 | 5 | 5 | 0 | 1 | 1 | yes |

The top-five pool produced a perfect carrier/codeword observation after
combining the same repeated payload across exact block starts.

## Interpretation

This is strong evidence that block distress should be handled by pooling before
geometry fallback. The high-pilot exact windows contain useful signed carrier
evidence even when a single-block controller would abstain because the block is
too costly or uncertain by itself.

For v2, the recovery stack should expose two related outputs:

1. block-vote attribution for fast decisions,
2. pooled block attribution for higher-assurance/offline decisions.

Geometry fallback should remain reserved for low-localization or clear
alignment distress. On localized repeated blocks, cross-block pooling is the
better first fallback.

