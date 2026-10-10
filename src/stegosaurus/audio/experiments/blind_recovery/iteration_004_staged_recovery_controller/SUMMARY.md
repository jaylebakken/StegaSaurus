# Iteration 004: Staged Recovery Controller

## Goal

Turn the duration-bank findings into a controller-shaped prototype. The
controller tries cheap geometry first, expands only after abstention, and
accepts only a unique low-burden Reed--Solomon success.

## Method

- Fresh 30-second synthetic cover for the default compact audit: seed `7900`.
- Fixed claimed-plan transport path: 4-byte handle, 16 parity symbols, 184
  logical carriers, four replicas, and the `500-3800 Hz` carrier band.
- Attacks: clean PCM and named `250 ms` leading crop.
- Stages:
  - `received_only`: received duration plus `0`.
  - `single_250ms_edge_loss`: received duration plus `250 ms`.
  - `broad_single_edge_loss`: received duration plus `125`, `375`, or `500 ms`.
- Controls: transformed unwatermarked source audio and wrong-secret decoding of
  the transformed watermarked audio.
- Acceptance: the first stage with a unique success and correction burden no
  greater than `8`.

## Expected Interpretation

This iteration is the first production-shaped prototype. It does not make the
watermark more robust, but it makes recovery policy explicit: staged expansion,
runtime accounting, ambiguity handling, control checks, and an RS-burden gate.

## Result

| Attack | Selected stage | Watermarked acceptances | Exact recoveries | Unwatermarked acceptances | Wrong-secret acceptances | Median attempts | Median RS cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `clean_pcm` | `received_only` | 1/1 | 1/1 | 0/1 | 0/1 | 1 | 4 |
| `leading_crop_025s` | `single_250ms_edge_loss` | 1/1 | 1/1 | 0/1 | 0/1 | 2 | 4 |

The controller preserved the iteration 003 recovery/control behavior while
avoiding full-bank evaluation for accepted watermarked cases. Clean audio
accepted after one duration hypothesis; the leading crop accepted after the
received-duration stage abstained and the declared `250 ms` edge-loss stage
succeeded.

The remaining production gap is baseline signal-quality prediction. Iteration
003 showed a seed where even clean watermarked audio abstained, so a production
pipeline still needs a preflight or confidence model that can separate "not
enough signal to spend more search" from "needs a different declared geometry
hypothesis."

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_004_staged_recovery_controller.run
```
