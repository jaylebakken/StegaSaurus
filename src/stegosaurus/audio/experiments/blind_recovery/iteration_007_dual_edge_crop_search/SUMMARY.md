# Iteration 007: Dual-Edge Crop Search

## Goal

Search for recovery after both a leading crop and a trailing crop. This turns
crop geometry into a two-dimensional bounded grid: total missing duration and
leading missing duration.

## Method

- Fresh 30-second synthetic cover: seed `7900`.
- Fixed claimed-plan transport path from the blind-recovery track.
- Geometry grid: total loss from `0` to `500 ms` in `125 ms` steps; for each
  total loss, leading loss ranges from `0` to that total in the same step.
- Scenarios:
  - `125 ms` leading plus `125 ms` trailing,
  - `250 ms` leading plus `250 ms` trailing,
  - `125 ms` leading plus `375 ms` trailing,
  - `375 ms` leading plus `125 ms` trailing.
- Controls are evaluated on the two symmetric lower-bound cases.

## Scope Boundary

This is claimed-plan recovery with bounded crop geometry. It is not arbitrary
edit synchronization, unknown-handle discovery, or full watermark localization
inside unrelated long-form audio.

## Result

| Metric | Value |
| --- | ---: |
| Geometry hypotheses per watermarked trial | 15 |
| Watermarked trials | 4 |
| Watermarked acceptances | 0 |
| Exact recoveries | 0 |
| Control trials | 2 |
| Control acceptances | 0 |
| Median watermarked attempts | 15 |

The current edge-mode reconstruction does not recover the compact dual-edge
crop grid, even when the correct total loss and leading-loss values are inside
the search space. The safe behavior is good: it abstains rather than accepting
controls or choosing a wrong payload. But this is a real capability boundary.

## Interpretation

Single-edge crop recovery does not automatically generalize to leading-plus-
trailing crops. Searching total loss plus leading share is necessary, but not
sufficient, because the current phase and local candidate-map assumptions were
tuned around one-edge timing modes. A production pipeline should treat dual-edge
crops as unsupported for now and return abstention unless a later localization
or windowing strategy recovers them.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_007_dual_edge_crop_search.run
```
