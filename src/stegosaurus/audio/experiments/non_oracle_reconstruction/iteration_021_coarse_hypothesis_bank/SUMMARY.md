# Iteration 021: Duration-Feasible Coarse Hypothesis Bank

## Goal

Test whether filtering coarse pilot offsets through the bounded one-edge-crop duration model before ranking can prevent all-erasure non-oracle decodes.

## Method

- New synthetic covers: seeds `7200-7209`, 30 seconds each.
- Fixed transport: 4-byte registry handle, 16 RS parity symbols, 20 protected bytes, 184 logical bits, four replicas, and the existing `500-3800 Hz` carrier band.
- Decoder: retain the top three offsets satisfying existing pilot evidence/probe gates **and** a blind duration-feasible center phase; reconstruct each, then rank only RS-successful candidates by decoder-visible correction burden and pilot evidence.
- Controls: independently transformed unwatermarked and wrong-secret audio.

## Results

| Crop | Single-center baseline | Bank exact recovery | Selected RS costs within `16` | Median selected RS cost | Controls accepted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Trailing `250 ms` | 8/10 | 9/10 | 9/9 | 9 | 0/20 |
| Leading `250 ms` | 8/10 | 10/10 | 10/10 | 9.5 | 0/20 |

The coarse beam recovered a formerly missed leading case and selected only correct decoded handles on this fresh fixture. The remaining trailing failure had no RS-successful hypothesis.

## Interpretation

Duration feasibility must be applied before coarse-offset commitment. This is the first post-020 change that improves unconditional blind crop recovery while keeping every selected result within the 16-symbol budget. It is smoke evidence on named synthetic crops only; it is not a claim of general crop, codec, DSP, recorded-audio, or perceptual robustness.

`RESULTS.json` retains all trial rows. Reproduce with:

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_021_coarse_hypothesis_bank.run
```
