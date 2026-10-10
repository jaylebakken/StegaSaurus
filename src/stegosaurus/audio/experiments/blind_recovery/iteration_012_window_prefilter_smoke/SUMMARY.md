# Iteration 012: Window Prefilter Smoke

## Goal

Replace exact repeated-block window knowledge with a cheap prefilter. The
experiment embeds five independent `30 s` blocks into a `2.5 min` synthetic
song, scores `30 s` windows every `15 s`, and runs full recovery only on the top
ranked windows.

## Method

- Synthetic song: five independent `30 s` watermarked blocks.
- Candidate windows: `30 s` length, `15 s` stride.
- Prefilter score: median local-pilot margin over the claimed carrier plan.
- Full recovery: received-duration stage on the top five windows.
- Voting: any-block and two-block acceptance.

## Scope Boundary

This is a localization smoke test, not a production locator. It still uses the
claimed carrier plan and synthetic block structure. Its job is to test whether a
cheap prefilter can reduce full-recovery windows before more expensive crop
fallbacks are considered.

## Result

| Metric | Value |
| --- | ---: |
| Candidate windows | 9 |
| Top windows recovered fully | 5 |
| Exact block starts in top five | 5 |
| Recovered windows after full recovery | 3 |
| Any-block vote | accept |
| Two-block vote | accept |
| Prefilter time | `1.82 s` |
| Full recovery time on top five | `8.99 s` |

Top-ranked windows:

| Rank | Start | Exact block start | Pilot score |
| ---: | ---: | --- | ---: |
| 1 | `0 s` | yes | `0.6165` |
| 2 | `120 s` | yes | `0.6130` |
| 3 | `30 s` | yes | `0.6045` |
| 4 | `60 s` | yes | `0.6017` |
| 5 | `90 s` | yes | `0.5831` |

The prefilter successfully selects all exact block starts from the `15 s`
sliding-window grid. Running full recovery only on those top five windows
recovers `3/5` blocks, matching the exact-window result from iteration 011.

## Recommendation

Use pilot-window prefiltering as the next localization primitive. The waterfall
should first score windows cheaply, keep the top candidates, then run the
received-duration and single-edge crop recovery stages only on those windows.
This keeps the expensive recovery path tied to plausible block locations.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_012_window_prefilter_smoke.run
```
