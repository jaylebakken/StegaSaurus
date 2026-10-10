# Iteration 011: Blind Attack Validation

## Goal

Validate the selected 6-byte registry-handle plus 14-symbol Reed--Solomon allocation with fully blind candidate-map reconstruction under the project's named codec, DSP, and crop transformations.

## Method

- Covers: ten fresh seeded, 30-second **synthetic music-like** variants with seeds `6600-6609`, disjoint from iteration 010.
- Encoder: iteration 005 contrastive calibration, the 4-pilot / 12-payload pair allocation, `500-3800 Hz` carrier band, and `0.95` relative difference.
- Transport: fixed 6-byte opaque registry handle, 14 Reed--Solomon parity symbols, 20 protected bytes, 3 framing/checksum bytes, 184 logical bits, and four physical replicas.
- Decoder: iteration 008 frozen blind thresholds: expected pilot score at least `0.00`, pilot gap at least `0.24`. It receives no encoder frame map.
- Attacks: clean PCM; MP3 at `64`, `96`, and `128 kbps`; 44.1 kHz resampling round trip; peak normalization to `0.90`; 30 dB white noise; 4 kHz low pass; 250 ms trailing crop; and 250 ms leading crop.
- Controls: an independently transformed unwatermarked source and wrong-secret watermark decode for every attack and cover. An accept requires exact equality with the known handle.

## Results

| Attack | Map diagnostic | Exact recovery | Median / maximum RS cost | Negative-control accepts |
| --- | --- | ---: | ---: | ---: |
| Clean PCM | Post-hoc original timeline | 10 / 10 | 9 / 14 | 0 / 20 |
| MP3 64 kbps | Post-hoc original timeline | 7 / 10 | 14 / 18 | 0 / 20 |
| MP3 96 kbps | Post-hoc original timeline | 9 / 10 | 9.5 / 15 | 0 / 20 |
| MP3 128 kbps | Post-hoc original timeline | 9 / 10 | 10 / 16 | 0 / 20 |
| 44.1 kHz resample round trip | Post-hoc original timeline | 10 / 10 | 9 / 14 | 0 / 20 |
| Peak normalize to 0.90 | Post-hoc original timeline | 10 / 10 | 9 / 14 | 0 / 20 |
| 30 dB white noise | Post-hoc original timeline | 8 / 10 | 12.5 / 24 | 0 / 20 |
| 4 kHz low pass | Post-hoc original timeline | 7 / 10 | 13 / 19 | 0 / 20 |
| 250 ms trailing crop | Timeline unaligned; not scored | 0 / 10 | 35 / 38 | 0 / 20 |
| 250 ms leading crop | Timeline unaligned; not scored | 0 / 10 | 32 / 35 | 0 / 20 |

All 100 attack trials completed without execution failures. Each row has ten transformed unwatermarked controls and ten transformed wrong-secret controls; none exactly returned the known six-byte handle. The median embedding SNR is `37.91 dB` across the shared ten embeddings.

For non-crop attacks, post-hoc selected-map accuracy remains high (`0.973-0.991` median), but lower pilot-map quality corresponds with increased RS damage under the 64 kbps MP3, 30 dB noise, and 4 kHz low-pass conditions. These diagnostics were never decoder inputs. Crop map diagnostics are intentionally omitted because comparing frame indices after a crop requires a realignment algorithm that this study does not implement.

## Interpretation Rules

- This study uses blind reconstruction. Encoder-selected source frame maps are never decoder inputs.
- Map-selection accuracy is post-hoc diagnostic data only. It is omitted for leading and trailing crops because their timelines cannot be compared to the original frame indices without a realignment algorithm.
- The covers are synthetic; this study cannot establish robustness on recorded speech, music, or general real-world audio.
- Do not claim a transformation as supported unless its own named result has exact recovery, zero negative-control accepts, and no alignment caveat.

## Interpretation

- On these ten disjoint **synthetic** covers, blind exact recovery is measured for clean PCM, the declared 44.1 kHz resample round trip, and peak normalization. This does not generalize to recorded audio.
- The named MP3, noise, and low-pass conditions are not reliable enough for a support claim: they each have one or more exact-recovery failures and Reed--Solomon costs above the 14-symbol budget.
- Both bounded crop conditions fail every trial, with median RS costs more than twice the correction budget. The immediate technical blocker is blind timeline synchronization or semantic-frame realignment before candidate-map reconstruction.
- The zero exact known-handle accepts in these limited controls are a useful regression signal, not a false-positive-rate estimate for a production registry or open-world detector.

## Decision

Keep the 6-byte handle + 14 parity allocation as the clean-channel candidate, but do not advance it as compression/DSP or crop robust. The next experiment should add a keyed sync/pilot-frame scan that searches bounded timeline offsets before local candidate ranking, then repeats the two crop conditions with the same frozen threshold and controls. A separately licensed recorded-audio corpus is required before any real-audio robustness evaluation.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_011_blind_attack_validation.run
```

The complete machine-readable output for all 100 attack trials and their 200 paired control decodes is archived in `RESULTS.json` beside this summary.
