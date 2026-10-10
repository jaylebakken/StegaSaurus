# Iteration 012: Offset-Scan Crop Realignment

## Goal

Test whether a secret-derived, bounded STFT timeline-offset scan can realign the blind local-pilot decoder before candidate ranking and improve the iteration 011 leading/trailing crop results.

## Method

- Covers and attacks: exactly reuse iteration 011's ten synthetic 30-second covers (`6600-6609`) and its `250 ms` leading and trailing crop transformations.
- Transport: unchanged 6-byte opaque registry handle, 14 Reed--Solomon parity symbols, 184 logical carrier bits, and four replicas.
- Encoder and payload decoder: unchanged contrastive `4`-pilot / `12`-payload profile and frozen local-pilot thresholds (`0.00` expected pilot, `0.24` best-minus-rival gap).
- Sync scan: rebuild the nominal 30-second STFT stratum geometry for each candidate offset from `-32` through `+32` frames (`±512 ms` at the current 256-sample hop / 16 kHz rate). Probe every eighth carrier using only secret-derived pilot signs, then accept the best offset only with predeclared evidence and runner-up-gap thresholds.
- Cropped carrier strata that no longer contain enough candidates become erasures. The decoder receives neither the original source audio nor encoder-selected frame maps.
- Controls: transformed unwatermarked and wrong-secret decodes for every trial/crop.

## Results

| Crop attack | Scan accepts | Median selected offset | Median post-hoc offset error | Exact recovery | Median / maximum RS cost | Median carrier erasures | Negative-control accepts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 250 ms trailing crop | 8 / 10 | 0 frames | 0 frames | 7 / 10 | 12 / 30 | 2 | 0 / 20 |
| 250 ms leading crop | 10 / 10 | 16 frames | 0 frames | 0 / 10 | 29.5 / 34 | 5.5 | 0 / 20 |

All twenty attacked decodes completed without execution failures. Every crop has ten independently transformed unwatermarked controls and ten wrong-secret controls; none exactly returned the known six-byte handle.

Against iteration 011's direct baseline (`0 / 10` for both crop directions), the bounded scan makes trailing-crop recovery possible: seven trials recover exactly, with median RS cost reduced from `35` to `12`. Two trailing scans abstain because their best-minus-runner evidence gaps are below the fixed `0.005` threshold; one accepted scan selects frame offset `13` rather than `0` and fails recovery.

The leading scan accepts every trial and selects the expected nearest `16`-frame offset in seven trials, but still recovers no tokens. The named 250 ms crop removes `4000` samples, which is `15.625` current STFT hops rather than an integer hop. We infer that choosing a nearest whole-frame timeline offset restores much of the keyed pilot evidence but does not restore the fractional-hop analysis-window phase needed for reliable payload scores. This is an inference from the measured split, not proof of a unique root cause.

## Interpretation Rules

- The known crop displacement is retained only as a post-hoc label; it is never an offset-scan input.
- This direct rerun on iteration 011's crop fixture isolates the alignment change. Any promising result must be repeated on fresh held-out covers before being generalized.
- A rejected scan is an intentional abstention that produces erasures, not an execution failure or an inferred offset.

## Interpretation

- The scan demonstrates that existing keyed local pilots can support bounded blind trailing-crop synchronization without consuming extra carrier capacity.
- It does not establish general crop robustness: trailing recovery is `7 / 10`, and leading recovery remains `0 / 10` under the same synthetic fixture.
- Leading-crop offset detection and payload recovery are separate problems. A coarse STFT-frame offset can be correct at the grid level while a sub-hop sample displacement still disrupts frame-local spectral carriers.
- The zero exact known-handle accepts are useful regression controls only, not an open-world false-positive estimate.

## Decision

Keep the bounded scan as a promising trailing-crop synchronization component, but do not treat it as a complete realignment solution. The next experiment should use the selected coarse frame offset to search a bounded **sample-level residual** within one hop, reframe/recompute the STFT at that residual, and repeat both crop directions with unchanged transport, controls, and attack parameters. Any gain must then be evaluated on fresh held-out covers and eventually a licensed recorded-audio corpus.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_012_offset_scan_crop_realignment.run
```

The complete machine-readable output for all twenty crop trials, their offset scores, and forty paired control decodes is archived in `RESULTS.json` beside this summary.
