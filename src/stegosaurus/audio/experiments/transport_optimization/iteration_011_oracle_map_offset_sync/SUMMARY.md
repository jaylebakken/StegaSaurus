# Iteration 011: Sync-Only Oracle Map Offset Recovery

## Goal

Resolve the 250 ms leading-crop failure from iteration 010 without using protected token data to choose alignment. The scanner must select alignment from fixed framing sync bits, then recover the full token with the resulting map translation.

## Method

- Cover set: the same ten seeded, calibrated 30-second synthetic variants from iterations 009 and 010.
- Crop: remove the first 250 ms of each watermarked waveform.
- Coarse scan: evaluate positive source-frame offsets from 0 through 32 STFT hops using only the 24 known framing-sync carrier bits.
- Residual scan: around the selected coarse hop offset, prepend zero samples at 16-sample increments across a two-hop window and rescore only sync bits.
- Extraction: retain original source-frame keys for pair and chip derivation while reading spectrum from the selected observed sample clock.
- Verification: exact known-token equality; no data-bit alignment score is used.

## Results

| Metric | Result |
| --- | ---: |
| Exact token recoveries | 10 / 10 |
| Median RS cost | 0 |
| Maximum RS cost | 4 / 12 parity symbols |
| Median sync matches | 24 / 24 |
| Coarse offsets selected | 15 or 16 frames |
| Residual sample offsets selected | 3952–4016 samples |

The 250 ms crop removes 4,000 samples, or 15.625 256-sample STFT hops. A whole-frame scan alone restored 8/10 variants because an integer hop cannot express this fractional offset. The bounded residual scan restored all 10 variants; its 16-sample sample-clock candidates include the true 4,000-sample crop position and nearby values that still decode within Reed--Solomon capacity.

## Regression

`src/stegosaurus/audio/tests/test_oracle_map_offset_sync.py` now requires a calibrated 30-second cover with a 250 ms leading crop to recover its exact token through the sync-only scan. This guards both alignment steps and the requirement to keep source-frame keys when deriving secret carrier pairs and chips.

## Interpretation Boundaries

- This solves a bounded **constant leading-offset** problem under retained oracle source maps.
- It does not reconstruct carrier maps independently, and it does not support arbitrary insertion/deletion edits, trailing-plus-leading complex edits, time scaling, or sample offsets outside the declared scan window.
- The residual search is encoder/decoder transform-model specific and was evaluated only on the named synthetic variant family.

## Decision

- Replace the iteration-010 characterization of the named 250 ms leading crop with this bounded sync-only oracle-map recovery result.
- Keep the regression test as a required guard before expanding crop or edit evaluations.
- Do not claim blind synchronization until the map itself can be reconstructed or scanned without retained source mappings.

## Next Step

Generalize the offset scan into a local sync-guided candidate-map search, then pre-register insertion, deletion, broader leading-crop, and time-scale experiments. Evaluate synchronization accuracy separately from token transport recovery.

## Reproduce

The complete machine-readable output for all ten leading-crop trials is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.transport_optimization.iteration_011_oracle_map_offset_sync.run
```
