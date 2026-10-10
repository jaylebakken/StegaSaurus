# Iteration 010: Calibrated Selector Transformation Study

## Goal

Measure exact opaque-token recovery after a pre-registered set of clean PCM, codec, DSP, normalization, noise, and crop transformations. The study uses iteration 009's calibrated post-round-trip margin selector and reports byte-level Reed--Solomon damage for every condition.

## Pre-Registered Method

- Cover set: ten seeded 30-second synthetic music-like variants with deterministic virtual timeline offsets.
- Transport: 8-byte token, 12 Reed--Solomon parity bytes, four copies, `relative_difference=0.95`, and extraction threshold `0.010`.
- Selector: two post-round-trip probe candidates per stratum, followed by a final calibrated map.
- Mapping: the source oracle map is retained for mapping-preserving transformations. Trailing crop uses that map and may yield missing trailing frames. Leading crop intentionally uses the unshifted map and is labeled alignment limited because crop realignment is not implemented.
- Attacks: PCM control; MP3 64, 96, and 128 kbps; 44.1 kHz round trip; 0.90 peak normalization; 30 dB white noise; 4 kHz low-pass; 250 ms trailing crop; and 250 ms leading crop.

## Results

| Condition | Map Interpretation | Exact Recovery | Median RS Cost | Median Unknown Byte Errors | Median Byte Erasures |
| --- | --- | ---: | ---: | ---: | ---: |
| Clean PCM | Preserved oracle map | 10 / 10 | 0 | 0 | 0 |
| MP3 64 kbps | Preserved oracle map | 10 / 10 | 0 | 0 | 0 |
| MP3 96 kbps | Preserved oracle map | 10 / 10 | 0 | 0 | 0 |
| MP3 128 kbps | Preserved oracle map | 10 / 10 | 0 | 0 | 0 |
| 44.1 kHz round trip | Preserved oracle map | 10 / 10 | 0 | 0 | 0 |
| Peak normalize 0.90 | Preserved oracle map | 10 / 10 | 0 | 0 | 0 |
| White noise 30 dB | Preserved oracle map | 10 / 10 | 0 | 0 | 0 |
| Low-pass 4 kHz | Preserved oracle map | 0 / 10 | 22 | 10 | 2 |
| Trailing crop 250 ms | Original map with possible trailing erasures | 10 / 10 | 0 | 0 | 0 |
| Leading crop 250 ms | Unrealigned original map | 0 / 10 | 36 | 16 | 4 |

No attack execution failed. Median embedding SNR was 42.26 dB across variants. The maximum RS cost for every passing condition was 2, within the 12-symbol parity budget. The 4 kHz low-pass condition reached a maximum RS cost of 30, and the leading crop reached 38.

## Interpretation Boundaries

- These are oracle-aligned results on one synthetic cover family. They do not establish independent blind decoding, production robustness, or general codec and corpus performance.
- MP3 success applies only to the named FFmpeg/LAME round trips and bitrates in this study, not arbitrary encoders, bitrates, music, speech, or editing workflows.
- The low-pass failure is consistent with the current 500–6000 Hz carrier band: a 4 kHz cutoff removes part of the assigned carrier spectrum.
- Trailing crop succeeds because most selected source-frame positions remain aligned and present. Leading crop fails because the current decoder has no insertion/deletion or non-hop crop realignment.

## Decision

- The calibrated selector passes the named clean, MP3, resampling, normalization, noise, and trailing-crop conditions under the oracle-map assumption.
- Do not claim support for leading crops, insertion/deletion edits, time scaling, or 4 kHz low-pass filtering.
- Before broadening robustness claims, implement deterministic decoder-side candidate-map reconstruction or local sync-guided scan, and repeat against held-out licensed audio.

## Next Step

Separate the carrier band into low-pass-tolerant and full-band profiles, then test calibrated selection under each profile. In parallel, prototype local synchronization recovery for leading crop offsets before running an edit-resilience benchmark.

## Reproduce

The complete machine-readable output for all 100 attack trials is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.transport_optimization.iteration_010_calibrated_attack_study.run
```
