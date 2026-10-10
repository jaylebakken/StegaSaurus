# Iteration 001: Clean Candidate-Map Reconstruction

## Goal

Measure the first non-oracle reconstruction baseline on clean audio. The decoder must regenerate carrier-frame candidates from the observed waveform and select a map without receiving the encoder's calibrated source-frame map. The retained oracle map is consulted only after decoding to score the reconstructed map.

## Method

- Covers: ten seeded, 30-second synthetic music-like variants.
- Encoder: the completed calibrated-margin transport configuration: 8-byte token, 12 Reed--Solomon parity symbols, four copies, `relative_difference=0.95`, and the `500-3800 Hz` carrier band.
- Decoder candidates: regenerate the top two observable high-quality frame candidates in every carrier stratum.
- Selection: fixed framing-sync carriers use their known bit sign. Unknown data carriers choose the four candidate ranks with the strongest signed four-copy consensus; this selection does not read known payload bits or the retained map.
- Controls: run the same procedure against the original unwatermarked cover and against the watermarked cover with a wrong secret. A control is counted only if it exactly returns the known input token.
- Success: the Reed--Solomon output must exactly equal the input token. The oracle map is used only for post-hoc candidate coverage and map-selection metrics.

## Results

| Metric | Result |
| --- | ---: |
| Exact token recoveries | 0 / 10 |
| Median / range RS cost | 29 / 24-34, with a 12-symbol budget |
| Median known carrier-bit errors | 28 / 20-37 |
| Median carrier erasures | 0 / 0-0 |
| Median oracle-candidate coverage | 99.32% / 99.05-99.86% |
| Median selected-map accuracy | 84.51% / 79.35-89.00% |
| Median sync-map accuracy | 98.96% / 97.92-100.00% |
| Median data-map accuracy | 82.27% / 76.25-87.34% |
| Unwatermarked exact-token false accepts | 0 / 10 |
| Wrong-secret exact-token false accepts | 0 / 10 |

## Interpretation

- Candidate availability is not the limiting factor: almost every calibrated oracle frame remains in the decoder's two observed candidates.
- Fixed sync bits provide enough information to select their frame candidates nearly perfectly on this clean fixture.
- The unknown data carrier rule is substantially weaker. It produces confident choices rather than erasures, leaving a median RS cost of 29 and no verified token recoveries.
- The two negative controls produced no exact known-token acceptance in this small study. That is not a false-positive-rate claim; the search budget, corpus, and sample count are far too limited for one.

## Decision

Do not extend this selection rule to attacks. The next non-oracle design should add decoder-observable map evidence adjacent to each data carrier, such as a protected local pilot pair or a deterministic selection rule whose stability is verified after the encoder round trip. That side information must be evaluated against its capacity, SNR, and false-accept costs before it is treated as a solution.

## Reproduce

The complete machine-readable result for all ten watermarked trials and both control outcomes is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_001_clean_candidate_map.run
```
