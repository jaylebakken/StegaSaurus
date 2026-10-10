# Iteration 032: Duration-Derived Edge-Mode Coarse Bank

## Goal

Prevent a coarse hypothesis near the leading-crop duration from excluding the equally plausible trailing-crop timeline before local candidate-map construction.

## Method

- Fresh 30-second synthetic covers: seeds `7700-7709`.
- Fixed transport: 4-byte handle, 16 RS parity symbols, 20 protected bytes, 184 logical carriers, four replicas, and the unchanged `500-3800 Hz` band.
- For every received crop, derive the bounded one-edge timing modes from sample loss: offset `0` for a trailing crop and floor/ceil of `missing_samples / hop_size` for a leading crop.
- Reconstruct all feasible modes with the existing local candidate selector; choose only a uniquely best RS-successful result using decoder-visible correction burden and pilot evidence.
- Controls: independently transformed unwatermarked and wrong-secret streams.

## Results

| Crop | Exact recovery | Selected RS costs within `16` | Median selected RS cost | Selected coarse offsets | Controls accepted |
| --- | ---: | ---: | ---: | --- | ---: |
| Trailing `250 ms` | 10/10 | 10/10 | 9.5 | `0` | 0/20 |
| Leading `250 ms` | 10/10 | 10/10 | 9.0 | `15`, `16` | 0/20 |

The selected offsets match the named single-edge timing modes: all trailing replays select `0`, while leading replays select the two frame-rounding possibilities around `4000 / 256 = 15.625` frames. This directly fixes the iteration 031 failure mode, where a leading-like offset excluded the true trailing map.

## Decision

For the declared 30-second synthetic fixture and named `250 ms` leading/trailing crop transforms, the duration-derived edge-mode bank is the first non-oracle synchronization policy to recover all fresh validation cases with post-hoc RS cost at most 16 and no selected negative controls. This is not a claim about other crop lengths, multi-edit timelines, codecs, DSP, recorded audio, adversarial inputs, false-positive rates, or perceptual transparency.

The next step is a separately seeded broader validation that includes clean PCM, multiple bounded crop durations, and the existing named transformations before any application-level promotion.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_032_edge_mode_coarse_bank.run
```
