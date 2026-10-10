# Iteration 008: Runtime Profile

## Goal

Measure the runtime cost of the current blind-recovery search modes. This helps
decide whether future localization should scan many crop/window hypotheses or
needs a cheaper prefilter.

## Method

- Fresh 30-second synthetic cover: seed `7900`.
- Timed modes:
  - clean audio with received-duration only,
  - `250 ms` leading crop with the recommended single-edge grid through
    `500 ms`,
  - `250 ms` leading plus `250 ms` trailing crop with the dual-edge grid from
    iteration 007.
- Each row records elapsed milliseconds, attempted hypotheses, decision, and
  exact recovery.

## Scope Boundary

This is a local wall-clock profile, not a portable benchmark. Timings are useful
for relative shape: single received-duration recovery is cheap, wider geometry
search is roughly proportional to attempted hypotheses, and localization over
many windows would multiply that cost.

## Result

| Mode | Decision | Exact recovery | Attempts | Elapsed |
| --- | --- | ---: | ---: | ---: |
| `clean_received_only` | accept | 1/1 | 1 | `2.20 s` |
| `leading_250ms_single_edge_grid` | accept | 1/1 | 3 | `9.03 s` |
| `lead250_trail250_dual_grid` | abstain | 0/1 | 15 | `33.34 s` |

The compact profile attempted `19` total hypotheses and took `44.57 s` on this
local run. The slow path is not JSON, policy ranking, or control logic; it is
the repeated STFT/reconstruction work per geometry hypothesis.

## Localization Implication

This matters for finding where a watermark is inside a larger cover. A naive
localization scan would multiply the geometry cost by the number of candidate
windows. For example, even the cheap received-duration hypothesis was about
`2.2 s` for one 30-second window on this machine, while a failed dual-edge grid
was about `33 s`.

The next localization design should therefore use a cheap prefilter before full
reconstruction. A plausible staged shape is:

1. Slide a coarse window and score keyed pilot evidence only.
2. Keep the top few candidate windows.
3. Run the single-edge `500 ms` crop grid only on those windows.
4. Reserve the dual-edge grid for explicit stress or offline analysis, because
   the current dual-edge search is both slow and non-recovering.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_008_runtime_profile.run
```
