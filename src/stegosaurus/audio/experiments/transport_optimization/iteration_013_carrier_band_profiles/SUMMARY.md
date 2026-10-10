# Iteration 013: Carrier-Band Profiles

## Goal

Determine whether restricting the attribution carrier band below a 4 kHz low-pass cutoff closes iteration 010's low-pass recovery gap while retaining clean PCM, 64 kbps MP3, and bounded 250 ms leading-crop recovery.

## Method

- Covers: ten seeded, calibrated 30-second synthetic music-like variants.
- Transport: 8-byte known token, 12 Reed--Solomon parity symbols, and four repeated carrier copies.
- Embedding: calibrated post-round-trip margin selection with `relative_difference=0.95` and a `0.01` extraction threshold.
- Profiles: baseline `500-6000 Hz`, guarded `500-3800 Hz`, and low-pass-safe `500-3200 Hz`.
- Attacks: clean PCM, 64 kbps MP3 round trip, 4 kHz low-pass filter, and a 250 ms leading crop.
- Mapping: clean, MP3, and low-pass extraction retain the encoder's source-frame map. The leading crop uses iteration 011's sync-only offset scan, but still translates that retained map.
- Success: the Reed--Solomon output must exactly equal the known input token. RS cost is `2 * unknown byte errors + byte erasures`, with a budget of 12.

## Results

| Carrier profile | Attack | Exact recovery | Median / maximum RS cost | Median embedding SNR |
| --- | --- | ---: | ---: | ---: |
| `500-6000 Hz` | Clean PCM | 10 / 10 | 0 / 2 | 42.26 dB |
| `500-6000 Hz` | MP3 64 kbps | 10 / 10 | 0 / 2 | 42.26 dB |
| `500-6000 Hz` | 4 kHz low-pass | 0 / 10 | 22 / 30 | 42.26 dB |
| `500-6000 Hz` | 250 ms leading crop | 10 / 10 | 0 / 4 | 42.26 dB |
| `500-3800 Hz` | Clean PCM | 10 / 10 | 0 / 2 | 41.66 dB |
| `500-3800 Hz` | MP3 64 kbps | 10 / 10 | 0 / 2 | 41.66 dB |
| `500-3800 Hz` | 4 kHz low-pass | 10 / 10 | 0 / 2 | 41.66 dB |
| `500-3800 Hz` | 250 ms leading crop | 10 / 10 | 0 / 4 | 41.66 dB |
| `500-3200 Hz` | Clean PCM | 10 / 10 | 0 / 2 | 41.35 dB |
| `500-3200 Hz` | MP3 64 kbps | 10 / 10 | 0 / 3 | 41.35 dB |
| `500-3200 Hz` | 4 kHz low-pass | 10 / 10 | 0 / 2 | 41.35 dB |
| `500-3200 Hz` | 250 ms leading crop | 10 / 10 | 0 / 2 | 41.35 dB |

## Interpretation

- The baseline's carriers above the low-pass cutoff caused the iteration-010 failure; its median RS cost of 22 exceeds the 12-symbol correction budget.
- Both restricted bands recovered every named condition on this fixture. The guarded `500-3800 Hz` profile is preferred for the next study because it passes all conditions while retaining slightly more embedding SNR than `500-3200 Hz`.
- This is only evidence for the declared synthetic covers and named transformations. It does not establish robustness to arbitrary low-pass implementations, codecs, speech, music corpora, adversarial attacks, or perceptual evaluation.
- None of these conditions independently reconstructs the calibrated encoder-side carrier map. The crop scanner solves a bounded constant offset only after retaining that map, so the result is not blind decoding.

## Decision

Use `500-3800 Hz` as the default candidate band for the next synchronization experiment. The next experiment should measure non-oracle candidate-map recovery on clean audio first, comparing each reconstructed frame path to the retained oracle map before extending it to transformations.

## Reproduce

The complete machine-readable result for all 120 observations is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.transport_optimization.iteration_013_carrier_band_profiles.run
```
